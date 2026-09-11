#include "provider.h"
#include "credential.h"
#include "pipe_client.h"

FaceKeyProvider::FaceKeyProvider()
    : _cRef(1)
    , _cpus(CPUS_INVALID)
    , _pCredential(nullptr)
    , _serviceAvailable(false)
{
}

FaceKeyProvider::~FaceKeyProvider() {
    if (_pCredential) {
        _pCredential->Release();
    }
}

HRESULT FaceKeyProvider::QueryInterface(REFIID riid, void** ppv) {
    static const QITAB qit[] = {
        QITABENT(FaceKeyProvider, ICredentialProvider),
        { nullptr },
    };
    return QISearch(this, qit, riid, ppv);
}

ULONG FaceKeyProvider::AddRef() {
    return InterlockedIncrement(&_cRef);
}

ULONG FaceKeyProvider::Release() {
    LONG cRef = InterlockedDecrement(&_cRef);
    if (!cRef) delete this;
    return cRef;
}

HRESULT FaceKeyProvider::SetUsageScenario(
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
    DWORD /*dwFlags*/)
{
    switch (cpus) {
    case CPUS_LOGON:
    case CPUS_UNLOCK_WORKSTATION:
    case CPUS_CREDUI:
        _cpus = cpus;

        // Check if FaceKey service is running
        {
            StatusResult status = PipeClient::GetStatus();
            _serviceAvailable = status.ready && status.profile_count > 0;
        }

        if (_serviceAvailable) {
            _pCredential = new(std::nothrow) FaceKeyCredential();
            if (_pCredential) {
                _pCredential->Initialize(_cpus);
            }
        }

        return S_OK;

    default:
        return E_INVALIDARG;
    }
}

HRESULT FaceKeyProvider::SetSerialization(
    const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* /*pcpcs*/)
{
    return E_NOTIMPL;
}

HRESULT FaceKeyProvider::Advise(
    ICredentialProviderEvents* /*pcpe*/,
    UINT_PTR /*upAdviseContext*/)
{
    return S_OK;
}

HRESULT FaceKeyProvider::UnAdvise() {
    return S_OK;
}

HRESULT FaceKeyProvider::GetFieldDescriptorCount(DWORD* pdwCount) {
    *pdwCount = FI_NUM_FIELDS;
    return S_OK;
}

HRESULT FaceKeyProvider::GetFieldDescriptorAt(
    DWORD dwIndex,
    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd)
{
    if (dwIndex >= FI_NUM_FIELDS || !ppcpfd)
        return E_INVALIDARG;

    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR* pfd =
        (CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*)CoTaskMemAlloc(
            sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR));
    if (!pfd) return E_OUTOFMEMORY;

    const auto& src = s_FieldDescriptors[dwIndex];
    pfd->dwFieldID = src.dwFieldID;
    pfd->cpft = src.cpft;
    pfd->guidFieldType = src.guidFieldType;

    if (src.pszLabel) {
        SHStrDupW(src.pszLabel, &pfd->pszLabel);
    } else {
        pfd->pszLabel = nullptr;
    }

    *ppcpfd = pfd;
    return S_OK;
}

HRESULT FaceKeyProvider::GetCredentialCount(
    DWORD* pdwCount,
    DWORD* pdwDefault,
    BOOL* pbAutoLogonCredential)
{
    if (!_serviceAvailable || !_pCredential) {
        *pdwCount = 0;
        *pdwDefault = CREDENTIAL_PROVIDER_NO_DEFAULT;
        *pbAutoLogonCredential = FALSE;
    } else {
        *pdwCount = 1;
        *pdwDefault = 0;
        *pbAutoLogonCredential = FALSE;
    }
    return S_OK;
}

HRESULT FaceKeyProvider::GetCredentialAt(
    DWORD dwIndex,
    ICredentialProviderCredential** ppcpc)
{
    if (dwIndex != 0 || !_pCredential)
        return E_INVALIDARG;

    return _pCredential->QueryInterface(IID_ICredentialProviderCredential,
                                        reinterpret_cast<void**>(ppcpc));
}
