#include "AudioApp.h"
#include <iostream>
#include <memory>
#include <thread>
#include <chrono>

#ifdef _WIN32
#include <windows.h>
#endif

// 工具：处理控制台编码
static inline void initConsoleUTF8() {
#ifdef _WIN32
    SetConsoleCP(65001);          
    SetConsoleOutputCP(65001);    
#endif
}

// 工具：用于静默后台运行 (Sndcpy++ 路由特性)
static inline void setConsoleVisibility(bool show) {
#ifdef _WIN32
    HWND hwnd = GetConsoleWindow();
    if (hwnd != NULL) {
        ShowWindow(hwnd, show ? SW_SHOW : SW_HIDE);
    }
#endif
}

void printUsage(const char* exeName) {
    std::cout << "用法说明:\n";
    std::cout << "  兼容 Sndcpy / VLC 命令模式 (完美支持预缓冲):\n";
    std::cout << "    " << exeName << " -Idummy --demux rawaud --network-caching=200 --play-and-exit tcp://localhost:28200\n\n";
    
    std::cout << "  自定义高级参数:\n";
    std::cout << "    -ip <IP>          # 指定IP (默认 127.0.0.1)\n";
    std::cout << "    -port <Port>      # 指定端口 (默认 8080)\n";
    std::cout << "    -ar <SampleRate>  # 指定采样率 (例如 48000, 96000)\n";
    std::cout << "    -ac <Channels>    # 指定通道数 (例如 2)\n";
    std::cout << "    -f <f32|s16>      # 指定音频位深格式\n";
    std::cout << "    -record <file>    # 同时开启麦克风录制\n";
    std::cout << "    -hidden / -Idummy # 隐藏控制台后台静默运行\n";
    std::cout << "    -show             # 强制显示控制台界面\n\n";

    std::cout << "  协议速记:\n";
    std::cout << "    tcp://127.0.0.1:28200   # TCP 客户端连接模式 (Sndcpy默认)\n";
    std::cout << "    udp://127.0.0.1:8080    # UDP 服务端监听模式 (FFmpeg推流测试)\n";
}

int main(int argc, char* argv[]) {
    initConsoleUTF8();

    if (argc > 1 && (std::string(argv[1]) == "-h" || std::string(argv[1]) == "--help")) {
        printUsage(argv[0]);
        return 0;
    }

    // 初始化默认配置
    AudioApp::NetConfig netConfig;
    AudioApp::RecordConfig recConfig;
    bool doRecord = false;
    bool doPlay = true;

    // 默认显示控制台。如果带有 -Idummy 或 -hidden 则隐藏。
    bool showConsole = true; 
    bool sndcpyModeTriggered = false;
    bool formatOverridden = false; 

    // 健壮的参数解析器
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];

        // 1. UI 可见性解析
        if (arg == "-hidden" || arg == "-Idummy") {
            showConsole = false;
            continue;
        } else if (arg == "-show") {
            showConsole = true;
            continue;
        }

        // 2. 预缓冲 Jitter Buffer 解析 (完美兼容 VLC --network-caching=200)
        if (arg.find("--network-caching=") == 0) {
            try {
                netConfig.networkCachingMs = std::stoi(arg.substr(18));
            } catch(...) {}
            continue;
        }

        // 3. 忽略其他 VLC 无效参数
        if (arg == "--demux" || arg == "rawaud" || arg == "--play-and-exit") {
            continue;
        } 
        
        // 4. 解析高级定制参数
        if (arg == "-ar" && i + 1 < argc) {
            netConfig.sampleRate = recConfig.sampleRate = std::stoi(argv[++i]);
            formatOverridden = true;
        } 
        else if (arg == "-ac" && i + 1 < argc) {
            netConfig.channels = recConfig.channels = std::stoi(argv[++i]);
            formatOverridden = true;
        } 
        else if (arg == "-f" && i + 1 < argc) {
            std::string fmt = argv[++i];
            netConfig.format = recConfig.format = (fmt == "s16") ? AudioApp::Format::S16 : AudioApp::Format::F32;
            formatOverridden = true;
        } 
        else if (arg == "-record" && i + 1 < argc) {
            recConfig.outputFile = argv[++i];
            doRecord = true;
        } 
        else if (arg == "-ip" && i + 1 < argc) {
            netConfig.ip = argv[++i];
        } 
        else if (arg == "-port" && i + 1 < argc) {
            netConfig.port = std::stoi(argv[++i]);
        }
        // 5. 解析 URI 连接串 (重点适配 Sndcpy)
        else if (arg.find("tcp://") == 0 || arg.find("udp://") == 0) {
            netConfig.protocol = (arg.find("tcp://") == 0) ? AudioApp::Protocol::TCP_CONNECT : AudioApp::Protocol::UDP_LISTEN;
            
            if (netConfig.protocol == AudioApp::Protocol::TCP_CONNECT) {
                sndcpyModeTriggered = true; // 识别到 TCP，大概率是 Sndcpy
            }

            std::string ipport = arg.substr(6);
            size_t colon = ipport.find(':');
            if (colon != std::string::npos) {
                netConfig.ip = ipport.substr(0, colon);
                if (netConfig.ip == "localhost") netConfig.ip = "127.0.0.1";
                netConfig.port = std::stoi(ipport.substr(colon + 1));
            }
        }
    }

    // 动态显隐控制台黑框
    setConsoleVisibility(showConsole);

    // [重磅适配] 如果检测到是 Sndcpy 发来的 TCP 请求，并且用户没有手动覆盖格式
    // 我们自动把接收格式切换为 Sndcpy 原生的 48kHz, s16le。
    if (sndcpyModeTriggered && !formatOverridden) {
        netConfig.sampleRate = 48000;
        netConfig.format = AudioApp::Format::S16;
        recConfig.sampleRate = 48000;
        recConfig.format = AudioApp::Format::S16;
    }

    // 如果处于显示模式，则打印日志
    if (showConsole) {
        std::cout << "==============================================\n";
        std::cout << " Sndcpy++ AudioRouter (跨平台音频路由与录制) \n";
        std::cout << "==============================================\n";
    }

    auto audioApp = std::make_shared<AudioApp>();

    if (doRecord) {
        if (!audioApp->startRecording(recConfig)) {
            if (showConsole) std::cerr << "[错误] 录制启动失败！\n";
        } else {
            if (showConsole) std::cout << "[录音状态] 正在录制至: " << recConfig.outputFile << "\n";
        }
    }

    if (doPlay) {
        if (!audioApp->startNetworkPlayback(netConfig)) {
            if (showConsole) std::cerr << "[错误] 网络音频接收失败！\n";
            return -1;
        } else {
            if (showConsole) {
                std::cout << "[网络状态] 协议: " << (netConfig.protocol == AudioApp::Protocol::TCP_CONNECT ? "TCP" : "UDP") 
                          << " | 目标: " << netConfig.ip << ":" << netConfig.port << "\n";
                std::cout << "[抗抖缓存] " << netConfig.networkCachingMs << " ms\n";
                std::cout << "[音频格式] 采样率: " << netConfig.sampleRate 
                          << "Hz | 通道数: " << netConfig.channels 
                          << " | 位深: " << (netConfig.format == AudioApp::Format::S16 ? "s16" : "f32") << "\n";
            }
        }
    }

    if (showConsole) {
        std::cout << "\n系统运行中... 按回车键[Enter] 即可退出并保存音频。\n";
        // Detached thread only keeps a weak reference, so it cannot outlive the app object.
        std::weak_ptr<AudioApp> weakAudioApp = audioApp;
        std::thread waitKey([weakAudioApp]() {
            std::cin.get();
            if (auto lockedAudioApp = weakAudioApp.lock()) {
                lockedAudioApp->stop();
            }
        });
        waitKey.detach();
        // 阻塞主线程，直到手动按下回车，或者因手机掉线/网络异常导致退出
        audioApp->wait();
    } else {
        // 后台静默模式：完美阻塞直到音频路由断开。一旦 Sndcpy/ADB 停用，程序自然光速自杀清理，绝无僵尸进程。
        audioApp->wait();
    }

    audioApp->stop();
    if (showConsole) std::cout << "清理完毕，已安全退出。\n";

    return 0;
}
