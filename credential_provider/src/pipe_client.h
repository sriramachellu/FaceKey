#pragma once
#include <string>

struct AuthResult {
    bool success;
    std::wstring user;
    double similarity;
    double spoof_score;
    std::string reason;
};

struct StatusResult {
    bool ready;
    bool gpu;
    int profile_count;
};

class PipeClient {
public:
    static AuthResult Authenticate(int timeout_sec = 10);
    static StatusResult GetStatus();
    static bool Shutdown();

private:
    static std::string SendCommand(const std::string& json_cmd);
};
