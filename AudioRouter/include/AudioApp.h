#pragma once
#include <string>
#include <memory>

class AudioApp {
public:
    struct Impl;

    // 音频格式定义 (f32 或 s16)
    enum class Format { F32, S16 };
    // 网络协议定义
    enum class Protocol { UDP_LISTEN, TCP_CONNECT };

    // 网络播放配置参数
    struct NetConfig {
        std::string ip = "127.0.0.1";
        unsigned short port = 8080;
        Protocol protocol = Protocol::UDP_LISTEN;
        int sampleRate = 44100;
        int channels = 2;
        Format format = Format::F32;
        int networkCachingMs = 200; // 新增：网络抗抖动缓存区大小(毫秒)，完美消除滋滋声
    };

    // 录制配置参数
    struct RecordConfig {
        std::string outputFile = "record.wav";
        int sampleRate = 44100;
        int channels = 2;
        Format format = Format::F32;
    };

    AudioApp();
    ~AudioApp();

    // 启动网络音频接收并播放 (兼容 UDP 监听 和 TCP 客户端)
    bool startNetworkPlayback(const NetConfig& config);

    // 启动本地麦克风录音，并保存为 wav 文件
    bool startRecording(const RecordConfig& config);

    // 等待音频路由/录制彻底结束 (阻塞直到网络掉线)
    void wait();
    
    // 停止所有路由和录制
    void stop();

    // 检查是否有音频路由或录制在进行中
    bool isRunning() const;

private:
    std::unique_ptr<Impl> pImpl;
};