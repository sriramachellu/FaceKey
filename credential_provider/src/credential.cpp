#include "credential.h"
#include "pipe_client.h"
#include <string>

FaceKeyCredential::FaceKeyCredential()
    : _cRef(1)
    , _cpus(CPUS_INVALID)
    , _pEvents(nullptr)
    , _faceAuthSuccess(false)
{
    StringCchCopyW(_statusText, ARRAYSIZE(_statusText), L"Face unlock ready");
    ZeroMemory(_password, sizeof(_password));
}

FaceKeyCredential::~FaceKeyCredential() {
    SecureZeroMemory(_password, sizeof(_password));
}

void FaceKeyCredential::Initialize(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus) {
    _cpus = cpus;
}

HRESULT FaceKeyCredential::QueryInterface(REFIID riid, void** ppv) {
    static const QITAB qit[] = {
        QITABENT(FaceKeyCredential, ICredentialProviderCredential),
        { nullptr },
    };
    return QISearch(this, qit, riid, ppv);
}

ULONG FaceKeyCredential::AddRef() {
    return InterlockedIncrement(&_cRef);
}

ULONG FaceKeyCredential::Release() {
    LONG cRef = InterlockedDecrement(&_cRef);
    if (!cRef) delete this;
    return cRef;
}

HRESULT FaceKeyCredential::Advise(ICredentialProviderCredentialEvents* pcpce) {
    if (_pEvents) _pEvents->Release();
    _pEvents = pcpce;
    if (_pEvents) _pEvents->AddRef();
    return S_OK;
}

HRESULT FaceKeyCredential::UnAdvise() {
    if (_pEvents) {
        _pEvents->Release();
        _pEvents = nullptr;
    }
    return S_OK;
}

HRESULT FaceKeyCredential::SetSelected(BOOL* pbAutoLogon) {
    *pbAutoLogon = FALSE;

    SetStatusText(L"Scanning your face...");

    // Launch face auth in background thread
    HANDLE hThread = CreateThread(nullptr, 0,
        [](LPVOID param) -> DWORD {
            FaceKeyCredential* self = (FaceKeyCredential*)param;

            AuthResult result = PipeClient::Authenticate(15);

            if (result.success) {
                self->_faceAuthSuccess = true;
                self->_matchedUser = result.user;

                WCHAR status[256];
                StringCchPrintfW(status, ARRAYSIZE(status),
                    L"Welcome, %s (%.0f%%)",
                    result.user.c_str(),
                    result.similarity * 100.0);
                self->SetStatusText(status);

                // For unlock: auto-submit if we have stored credentials
                // For logon: show password field for first-time setup
            } else {
                WCHAR status[256];
                std::wstring reason;
                if (!result.reason.empty()) {
                    int sz = MultiByteToWideChar(CP_UTF8, 0,
                        result.reason.c_str(), -1, nullptr, 0);
                    reason.resize(sz);
                    MultiByteToWideChar(CP_UTF8, 0,
                        result.reason.c_str(), -1, &reason[0], sz);
                }
                StringCchPrintfW(status, ARRAYSIZE(status),
                    L"Face auth failed: %s",
                    reason.empty() ? L"unknown" : reason.c_str());
                self->SetStatusText(status);

                // Show password field as fallback
                if (self->_pEvents) {
                    self->_pEvents->SetFieldState(nullptr, FI_PASSWORD,
                        CPFS_DISPLAY_IN_SELECTED_TILE);
                    self->_pEvents->SetFieldState(nullptr, FI_SUBMIT_BUTTON,
                        CPFS_DISPLAY_IN_SELECTED_TILE);
                }
            }

            return 0;
        },
        this, 0, nullptr);

    if (hThread) CloseHandle(hThread);

    return S_OK;
}

HRESULT FaceKeyCredential::SetDeselected() {
    _faceAuthSuccess = false;
    SecureZeroMemory(_password, sizeof(_password));
    SetStatusText(L"Face unlock ready");
    return S_OK;
}

void FaceKeyCredential::SetStatusText(PCWSTR text) {
    StringCchCopyW(_statusText, ARRAYSIZE(_statusText), text);
    if (_pEvents) {
        _pEvents->SetFieldString(nullptr, FI_STATUS, _statusText);
    }
}

HRESULT FaceKeyCredential::GetFieldState(
    DWORD dwFieldID,
    CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
    CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis)
{
    if (dwFieldID >= FI_NUM_FIELDS) return E_INVALIDARG;

    const FIELD_STATE_PAIR* pairs =
        (_cpus == CPUS_UNLOCK_WORKSTATION)
            ? s_FieldStatePairsUnlock
            : s_FieldStatePairsLogon;

    *pcpfs = pairs[dwFieldID].cpfs;
    *pcpfis = pairs[dwFieldID].cpfis;
    return S_OK;
}

HRESULT FaceKeyCredential::GetStringValue(DWORD dwFieldID, PWSTR* ppwsz) {
    switch (dwFieldID) {
    case FI_LABEL:
        return SHStrDupW(L"FaceKey — Face Unlock", ppwsz);
    case FI_STATUS:
        return SHStrDupW(_statusText, ppwsz);
    case FI_PASSWORD:
        return SHStrDupW(L"", ppwsz);
    default:
        return E_INVALIDARG;
    }
}

HRESULT FaceKeyCredential::GetBitmapValue(DWORD dwFieldID, HBITMAP* phbmp) {
    if (dwFieldID != FI_ICON) return E_INVALIDARG;

    // Create a simple 48x48 blue circle bitmap as the tile icon
    HDC hdc = GetDC(nullptr);
    HDC memDC = CreateCompatibleDC(hdc);
    HBITMAP hBmp = CreateCompatibleBitmap(hdc, 48, 48);
    HBITMAP hOld = (HBITMAP)SelectObject(memDC, hBmp);

    // Fill background white
    RECT rc = { 0, 0, 48, 48 };
    HBRUSH bgBrush = CreateSolidBrush(RGB(255, 255, 255));
    FillRect(memDC, &rc, bgBrush);
    DeleteObject(bgBrush);

    // Draw blue circle (accent color #0078D4)
    HBRUSH circleBrush = CreateSolidBrush(RGB(0, 120, 212));
    HPEN circlePen = CreatePen(PS_SOLID, 2, RGB(0, 120, 212));
    SelectObject(memDC, circleBrush);
    SelectObject(memDC, circlePen);
    Ellipse(memDC, 4, 4, 44, 44);
    DeleteObject(circleBrush);
    DeleteObject(circlePen);

    // Draw simple face outline (white)
    HPEN facePen = CreatePen(PS_SOLID, 2, RGB(255, 255, 255));
    SelectObject(memDC, facePen);
    SelectObject(memDC, GetStockObject(NULL_BRUSH));
    // Head
    Ellipse(memDC, 14, 8, 34, 32);
    // Eyes
    Ellipse(memDC, 18, 16, 22, 20);
    Ellipse(memDC, 26, 16, 30, 20);
    // Mouth
    Arc(memDC, 18, 20, 30, 32, 30, 26, 18, 26);
    DeleteObject(facePen);

    SelectObject(memDC, hOld);
    DeleteDC(memDC);
    ReleaseDC(nullptr, hdc);

    *phbmp = hBmp;
    return S_OK;
}

HRESULT FaceKeyCredential::GetCheckboxValue(DWORD, BOOL*, PWSTR*) {
    return E_NOTIMPL;
}

HRESULT FaceKeyCredential::GetSubmitButtonValue(DWORD dwFieldID, DWORD* pdwAdjacentTo) {
    if (dwFieldID != FI_SUBMIT_BUTTON) return E_INVALIDARG;
    *pdwAdjacentTo = FI_PASSWORD;
    return S_OK;
}

HRESULT FaceKeyCredential::GetComboBoxValueCount(DWORD, DWORD*, DWORD*) {
    return E_NOTIMPL;
}

HRESULT FaceKeyCredential::GetComboBoxValueAt(DWORD, DWORD, PWSTR*) {
    return E_NOTIMPL;
}

HRESULT FaceKeyCredential::SetStringValue(DWORD dwFieldID, PCWSTR pwz) {
    if (dwFieldID == FI_PASSWORD) {
        StringCchCopyW(_password, ARRAYSIZE(_password), pwz);
        return S_OK;
    }
    return E_INVALIDARG;
}

HRESULT FaceKeyCredential::SetCheckboxValue(DWORD, BOOL) {
    return E_NOTIMPL;
}

HRESULT FaceKeyCredential::SetComboBoxSelectedValue(DWORD, DWORD) {
    return E_NOTIMPL;
}

HRESULT FaceKeyCredential::CommandLinkClicked(DWORD) {
    return E_NOTIMPL;
}

HRESULT FaceKeyCredential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
    PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon)
{
    *pcpgsr = CPGSR_NO_CREDENTIAL_NOT_FINISHED;

    if (!_faceAuthSuccess && wcslen(_password) == 0) {
        SHStrDupW(L"Face auth required or enter password", ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_ERROR;
        return S_OK;
    }

    // Get current username for unlock, or matched user for logon
    WCHAR username[256] = {};
    WCHAR domain[256] = {};
    DWORD usernameLen = ARRAYSIZE(username);
    DWORD domainLen = ARRAYSIZE(domain);

    if (_cpus == CPUS_UNLOCK_WORKSTATION) {
        GetUserNameW(username, &usernameLen);
        // Domain from environment
        DWORD envLen = GetEnvironmentVariableW(L"USERDOMAIN", domain, domainLen);
        if (envLen == 0) {
            GetComputerNameW(domain, &domainLen);
        }
    } else {
        // For logon, use the matched user name
        if (_faceAuthSuccess && !_matchedUser.empty()) {
            StringCchCopyW(username, ARRAYSIZE(username), _matchedUser.c_str());
        }
        GetComputerNameW(domain, &domainLen);
    }

    // If face auth succeeded but no password stored, report partial success
    if (_faceAuthSuccess && wcslen(_password) == 0) {
        SHStrDupW(L"Face verified — enter password to complete login",
                  ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_WARNING;

        // Show password field
        if (_pEvents) {
            _pEvents->SetFieldState(nullptr, FI_PASSWORD,
                CPFS_DISPLAY_IN_SELECTED_TILE);
            _pEvents->SetFieldState(nullptr, FI_SUBMIT_BUTTON,
                CPFS_DISPLAY_IN_SELECTED_TILE);
        }

        *pcpgsr = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        return S_OK;
    }

    // Pack credentials for Windows logon
    HRESULT hr = PackCredentials(domain, username, _password, pcpcs);

    if (SUCCEEDED(hr)) {
        *pcpgsr = CPGSR_RETURN_CREDENTIAL_FINISHED;
        *pcpsiOptionalStatusIcon = CPSI_SUCCESS;
    } else {
        *pcpgsr = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        SHStrDupW(L"Failed to package credentials", ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_ERROR;
    }

    SecureZeroMemory(_password, sizeof(_password));
    return hr;
}

HRESULT FaceKeyCredential::PackCredentials(
    PCWSTR domain, PCWSTR username, PCWSTR password,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs)
{
    DWORD cbAuth = 0;

    // First call to get buffer size
    CredPackAuthenticationBufferW(
        0, (PWSTR)username, (PWSTR)password,
        nullptr, &cbAuth);

    if (cbAuth == 0) return E_FAIL;

    pcpcs->rgbSerialization = (BYTE*)CoTaskMemAlloc(cbAuth);
    if (!pcpcs->rgbSerialization) return E_OUTOFMEMORY;

    if (!CredPackAuthenticationBufferW(
            0, (PWSTR)username, (PWSTR)password,
            pcpcs->rgbSerialization, &cbAuth))
    {
        CoTaskMemFree(pcpcs->rgbSerialization);
        pcpcs->rgbSerialization = nullptr;
        return HRESULT_FROM_WIN32(GetLastError());
    }

    pcpcs->cbSerialization = cbAuth;
    pcpcs->clsidCredentialProvider = CLSID_FaceKeyProvider;

    // Use Negotiate auth package
    ULONG authPackage = 0;
    HANDLE hLsa;
    NTSTATUS status = LsaConnectUntrusted(&hLsa);
    if (SUCCEEDED(HRESULT_FROM_NT(status))) {
        LSA_STRING lsaName;
        lsaName.Buffer = (PCHAR)"Negotiate";
        lsaName.Length = (USHORT)strlen(lsaName.Buffer);
        lsaName.MaximumLength = lsaName.Length + 1;
        LsaLookupAuthenticationPackage(hLsa, &lsaName, &authPackage);
        LsaDeregisterLogonProcess(hLsa);
    }

    pcpcs->ulAuthenticationPackage = authPackage;

    return S_OK;
}

HRESULT FaceKeyCredential::ReportResult(
    NTSTATUS ntsStatus, NTSTATUS /*ntsSubstatus*/,
    PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon)
{
    if (SUCCEEDED(HRESULT_FROM_NT(ntsStatus))) {
        *pcpsiOptionalStatusIcon = CPSI_SUCCESS;
    } else {
        SHStrDupW(L"Authentication failed. Try again or use password.",
                  ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_ERROR;

        // Show password fallback
        if (_pEvents) {
            _pEvents->SetFieldState(nullptr, FI_PASSWORD,
                CPFS_DISPLAY_IN_SELECTED_TILE);
            _pEvents->SetFieldState(nullptr, FI_SUBMIT_BUTTON,
                CPFS_DISPLAY_IN_SELECTED_TILE);
        }
    }
    return S_OK;
}
