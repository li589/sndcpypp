// 强制指定 Windows 版本为 Win7 及以上
#ifdef _WIN32
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#endif

#define ASIO_STANDALONE
#include <asio.hpp>

// 关闭不需要的解码器，加快编译速度并避开 SIMD
#define MA_NO_MP3
#define MA_NO_FLAC
#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"

#include "AudioApp.h"
#include <iostream>
#include <thread>
#include <vector>
#include <atomic>

// 工具函数：转换内部格式到 miniaudio 格式
static ma_format get_ma_format(AudioApp::Format fmt) {
    return (fmt == AudioApp::Format::S16) ? ma_format_s16 : ma_format_f32;
}

struct AudioApp::Impl {
    ma_device playbackDevice;
    ma_device captureDevice;
    ma_encoder encoder;
    ma_pcm_rb ringBuffer; 
    
    asio::io_context io_context;
    std::unique_ptr<asio::ip::udp::socket> udpSocket;
    std::unique_ptr<asio::ip::tcp::socket> tcpSocket;
    std::thread networkThread;
    
    std::atomic<bool> isPlaying{false};
    std::atomic<bool> isRecording{false};
    
    // === 核心抗抖动缓冲 (Jitter Buffer) 机制变量 ===
    std::atomic<bool> isBuffering{true};  // 缓冲状态机标记
    ma_uint32 prebufferFrames = 0;        // 阈值：需要攒够多少帧才开始播放
    
    std::vector<uint8_t> recvBuffer;
    
    // 缓存运行时格式参数
    int channels = 2;
    ma_format format = ma_format_f32;
    size_t bytesPerFrame = 8; // f32*2 = 8 bytes

    Impl() : recvBuffer(65536) {} // 增大接收缓冲应对高频/TCP流
};

// --- 音频硬件播放回调 (硬件向我们要数据) ---
void playback_data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount) {
    AudioApp::Impl* pImpl = static_cast<AudioApp::Impl*>(pDevice->pUserData);
    
    // 获取当前环形缓冲区有多少数据可读
    ma_uint32 availableToRead = ma_pcm_rb_available_read(&pImpl->ringBuffer);

    // ==========================================
    // 【抗抖动机制】缓冲期判断逻辑
    // ==========================================
    if (pImpl->isBuffering) {
        if (availableToRead >= pImpl->prebufferFrames) {
            // 缓存攒够了，退出缓冲状态，开始输出声音
            pImpl->isBuffering = false; 
        } else {
            // 还在攒缓存，输出静音，直接返回，避免弹出半帧产生噪音
            memset(pOutput, 0, frameCount * pImpl->bytesPerFrame);
            return;
        }
    }

    // ==========================================
    // 正常拉取音频逻辑
    // ==========================================
    ma_uint32 framesToRead = frameCount;
    void* pReadBuffer;
    
    ma_pcm_rb_acquire_read(&pImpl->ringBuffer, &framesToRead, &pReadBuffer);
    
    if (framesToRead > 0) {
        memcpy(pOutput, pReadBuffer, framesToRead * pImpl->bytesPerFrame);
        ma_pcm_rb_commit_read(&pImpl->ringBuffer, framesToRead);
    }
    
    // 如果实际读到的不够硬件要的 (发生欠流 Underflow)
    if (framesToRead < frameCount) {
        size_t offset = framesToRead * pImpl->bytesPerFrame;
        size_t remainingBytes = (frameCount - framesToRead) * pImpl->bytesPerFrame;
        memset(static_cast<uint8_t*>(pOutput) + offset, 0, remainingBytes);

        // 【极度关键】：发生欠流说明网络断档了，为了不产生连续的“滋滋”声，
        // 强制退回缓冲状态机，重新攒够 network-caching 毫秒后再发声。
        pImpl->isBuffering = true;
    }
}

// --- 音频硬件麦克风录音回调 (硬件把数据交给我们) ---
void capture_data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount) {
    AudioApp::Impl* pImpl = static_cast<AudioApp::Impl*>(pDevice->pUserData);

    // =========================================================================
    // 【可视化扩展点 1】 本地麦克风录音 PCM 裸流成型点
    // 当前缓冲: pInput (只读), 包含了 frameCount 帧的麦克风声音。
    // =========================================================================

    if (pImpl->isRecording) {
        ma_encoder_write_pcm_frames(&pImpl->encoder, pInput, frameCount, NULL);
    }
}

AudioApp::AudioApp() : pImpl(std::make_unique<Impl>()) {}
AudioApp::~AudioApp() { stop(); }

bool AudioApp::startNetworkPlayback(const NetConfig& config) {
    pImpl->channels = config.channels;
    pImpl->format = get_ma_format(config.format);
    pImpl->bytesPerFrame = config.channels * ma_get_bytes_per_sample(pImpl->format);
    
    // 计算并设置预缓冲阈值 (毫秒转为帧数)
    pImpl->prebufferFrames = static_cast<ma_uint32>((config.sampleRate * config.networkCachingMs) / 1000.0f);
    pImpl->isBuffering = (config.networkCachingMs > 0);

    try {
        if (config.protocol == Protocol::TCP_CONNECT) {
            pImpl->tcpSocket = std::make_unique<asio::ip::tcp::socket>(pImpl->io_context);
            asio::ip::tcp::resolver resolver(pImpl->io_context);
            auto endpoints = resolver.resolve(config.ip, std::to_string(config.port));
            
            // 针对 Sndcpy 的 adb forward 加大重试力度 (重试15次，约耗时3秒，防止Sndcpy启动过慢)
            int retries = 15;
            while(retries--) {
                try {
                    asio::connect(*pImpl->tcpSocket, endpoints);
                    break; // 连接成功
                } catch(...) {
                    if (retries == 0) throw; // 最后一次还是失败抛出异常
                    std::this_thread::sleep_for(std::chrono::milliseconds(200));
                }
            }
        } else {
            pImpl->udpSocket = std::make_unique<asio::ip::udp::socket>(
                pImpl->io_context, 
                asio::ip::udp::endpoint(asio::ip::make_address(config.ip), config.port)
            );
        }
    } catch (std::exception& e) {
        std::cerr << "网络绑定/连接失败: " << e.what() << "\n";
        return false;
    }

    // 初始化环形缓冲，预留 2 秒钟的缓冲区大小
    if (ma_pcm_rb_init(pImpl->format, config.channels, config.sampleRate * 2, NULL, NULL, &pImpl->ringBuffer) != MA_SUCCESS) {
        pImpl->udpSocket.reset();
        pImpl->tcpSocket.reset();
        return false;
    }

    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_playback);
    deviceConfig.playback.format   = pImpl->format;
    deviceConfig.playback.channels = config.channels;     
    deviceConfig.sampleRate        = config.sampleRate; 
    deviceConfig.dataCallback      = playback_data_callback;
    deviceConfig.pUserData         = pImpl.get();

    if (ma_device_init(NULL, &deviceConfig, &pImpl->playbackDevice) != MA_SUCCESS) {
        ma_pcm_rb_uninit(&pImpl->ringBuffer);
        pImpl->udpSocket.reset();
        pImpl->tcpSocket.reset();
        return false;
    }

    if (ma_device_start(&pImpl->playbackDevice) != MA_SUCCESS) {
        ma_device_uninit(&pImpl->playbackDevice);
        ma_pcm_rb_uninit(&pImpl->ringBuffer);
        pImpl->udpSocket.reset();
        pImpl->tcpSocket.reset();
        return false;
    }

    pImpl->isPlaying = true;

    pImpl->networkThread = std::thread([this, config]() {
        asio::ip::udp::endpoint sender_endpoint;
        while(pImpl->isPlaying) {
            std::error_code ec;
            size_t len = 0;
            
            if (config.protocol == Protocol::TCP_CONNECT) {
                len = pImpl->tcpSocket->read_some(asio::buffer(pImpl->recvBuffer), ec);
                if (ec == asio::error::eof || ec == asio::error::connection_reset) break;// Android掉线，退出循环
            } else {
                len = pImpl->udpSocket->receive_from(asio::buffer(pImpl->recvBuffer), sender_endpoint, 0, ec);
            }
            
            if (ec || len == 0) {
                if (!pImpl->isPlaying) break;
                // 防止极端情况下 len==0 但没有 error 时的死循环空转飙升 CPU
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
                continue;
            }

            ma_uint32 framesToProcess = static_cast<ma_uint32>(len / pImpl->bytesPerFrame);
            void* pWriteBuffer;
            
            ma_pcm_rb_acquire_write(&pImpl->ringBuffer, &framesToProcess, &pWriteBuffer);
            if (framesToProcess > 0) {
                memcpy(pWriteBuffer, pImpl->recvBuffer.data(), framesToProcess * pImpl->bytesPerFrame);
                ma_pcm_rb_commit_write(&pImpl->ringBuffer, framesToProcess);

                // =========================================================================
                // 【可视化扩展点 2】 网络播放 PCM 裸流成型点
                // 数据源: pImpl->recvBuffer.data()
                // =========================================================================
            }
        }
        // 跳出循环后，主动将播放状态标记为 false，以便解除主程序的阻塞
        pImpl->isPlaying = false;
    });
    
    return true;
}

bool AudioApp::startRecording(const RecordConfig& config) {
    ma_format ma_fmt = get_ma_format(config.format);
    ma_encoder_config encoderConfig = ma_encoder_config_init(ma_encoding_format_wav, ma_fmt, config.channels, config.sampleRate);
    
    if (ma_encoder_init_file(config.outputFile.c_str(), &encoderConfig, &pImpl->encoder) != MA_SUCCESS) {
        std::cerr << "无法打开文件进行录制: " << config.outputFile << "\n";
        return false;
    }

    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_capture);
    deviceConfig.capture.format   = ma_fmt;
    deviceConfig.capture.channels = config.channels;
    deviceConfig.sampleRate       = config.sampleRate;
    deviceConfig.dataCallback     = capture_data_callback;
    deviceConfig.pUserData        = pImpl.get();

    if (ma_device_init(NULL, &deviceConfig, &pImpl->captureDevice) != MA_SUCCESS) {
        ma_encoder_uninit(&pImpl->encoder);
        return false;
    }

    if (ma_device_start(&pImpl->captureDevice) != MA_SUCCESS) {
        ma_device_uninit(&pImpl->captureDevice);
        ma_encoder_uninit(&pImpl->encoder);
        return false;
    }

    pImpl->isRecording = true;
    return true;
}

void AudioApp::stop() {
    if (pImpl->isPlaying) {
        pImpl->isPlaying = false;
        if (pImpl->udpSocket) {
            std::error_code ec; pImpl->udpSocket->close(ec); 
        }
        if (pImpl->tcpSocket) {
            std::error_code ec; pImpl->tcpSocket->close(ec); 
        }
        if (pImpl->networkThread.joinable()) {
            pImpl->networkThread.join();
        }
        ma_device_uninit(&pImpl->playbackDevice);
        ma_pcm_rb_uninit(&pImpl->ringBuffer);
    }

    if (pImpl->isRecording) {
        pImpl->isRecording = false;
        ma_device_uninit(&pImpl->captureDevice);
        ma_encoder_uninit(&pImpl->encoder);
    }
}

bool AudioApp::isRunning() const {
    return pImpl->isPlaying || pImpl->isRecording;
}

void AudioApp::wait() {
    if (pImpl->networkThread.joinable()) {
        // 如果是网络播放模式，阻塞等待网络线程结束
        pImpl->networkThread.join();
    } else {
        // 如果仅为本地麦克风录音模式，轮询等待停止标志
        while (pImpl->isRecording) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
}
