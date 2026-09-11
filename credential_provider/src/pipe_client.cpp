#include "pipe_client.h"
#include "common.h"
#include <string>
#include <vector>

static std::wstring Utf8ToWide(const std::string& str) {
    if (str.empty()) return L"";
    int sz = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), (int)str.size(), nullptr, 0);
    std::wstring result(sz, 0);
    MultiByteToWideChar(CP_UTF8, 0, str.c_str(), (int)str.size(), &result[0], sz);
    return result;
}

static std::string ExtractJsonString(const std::string& json, const std::string& key) {
    std::string search = "\"" + key + "\":";
    auto pos = json.find(search);
    if (pos == std::string::npos) return "";

    pos += search.size();
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;

    if (pos >= json.size()) return "";

    if (json[pos] == '"') {
        pos++;
        auto end = json.find('"', pos);
        if (end == std::string::npos) return "";
        return json.substr(pos, end - pos);
    }

    auto end = json.find_first_of(",}", pos);
    if (end == std::string::npos) end = json.size();
    std::string val = json.substr(pos, end - pos);
    while (!val.empty() && (val.back() == ' ' || val.back() == '\n')) val.pop_back();
    return val;
}

static double ExtractJsonDouble(const std::string& json, const std::string& key) {
    std::string val = ExtractJsonString(json, key);
    if (val.empty()) return 0.0;
    try { return std::stod(val); } catch (...) { return 0.0; }
}

static bool ExtractJsonBool(const std::string& json, const std::string& key) {
    return ExtractJsonString(json, key) == "true";
}

std::string PipeClient::SendCommand(const std::string& json_cmd) {
    HANDLE pipe = CreateFileW(
        FACEKEY_PIPE_NAME,
        GENERIC_READ | GENERIC_WRITE,
        0, nullptr,
        OPEN_EXISTING, 0, nullptr
    );

    if (pipe == INVALID_HANDLE_VALUE) {
        return R"({"status":"error","reason":"pipe_connect_failed"})";
    }

    DWORD mode = PIPE_READMODE_MESSAGE;
    SetNamedPipeHandleState(pipe, &mode, nullptr, nullptr);

    DWORD written = 0;
    WriteFile(pipe, json_cmd.c_str(), (DWORD)json_cmd.size(), &written, nullptr);

    char buffer[PIPE_BUFFER_SIZE] = {};
    DWORD bytesRead = 0;
    BOOL ok = ReadFile(pipe, buffer, PIPE_BUFFER_SIZE - 1, &bytesRead, nullptr);
    CloseHandle(pipe);

    if (!ok || bytesRead == 0) {
        return R"({"status":"error","reason":"pipe_read_failed"})";
    }

    buffer[bytesRead] = '\0';
    return std::string(buffer);
}

AuthResult PipeClient::Authenticate(int timeout_sec) {
    char cmd[128];
    StringCbPrintfA(cmd, sizeof(cmd),
        R"({"command":"authenticate","timeout":%d})", timeout_sec);

    std::string response = SendCommand(cmd);

    AuthResult result = {};
    std::string status = ExtractJsonString(response, "status");

    if (status == "success") {
        result.success = true;
        result.user = Utf8ToWide(ExtractJsonString(response, "user"));
        result.similarity = ExtractJsonDouble(response, "similarity");
        result.spoof_score = ExtractJsonDouble(response, "spoof_score");
    } else {
        result.success = false;
        result.reason = ExtractJsonString(response, "reason");
    }

    return result;
}

StatusResult PipeClient::GetStatus() {
    std::string response = SendCommand(R"({"command":"status"})");

    StatusResult result = {};
    result.ready = ExtractJsonString(response, "status") == "ready";
    result.gpu = ExtractJsonBool(response, "gpu");

    // Count profiles from the JSON array (simple count of commas + 1)
    auto pos = response.find("\"profiles\"");
    if (pos != std::string::npos) {
        auto start = response.find('[', pos);
        auto end = response.find(']', pos);
        if (start != std::string::npos && end != std::string::npos) {
            std::string arr = response.substr(start, end - start + 1);
            if (arr.size() > 2) {
                result.profile_count = 1;
                for (char c : arr) if (c == ',') result.profile_count++;
            }
        }
    }

    return result;
}

bool PipeClient::Shutdown() {
    std::string response = SendCommand(R"({"command":"shutdown"})");
    return ExtractJsonString(response, "status") == "ok";
}
