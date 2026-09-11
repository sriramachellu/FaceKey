#include "common.h"
#include "provider.h"

static LONG g_cRef = 0;
static HINSTANCE g_hInstance = nullptr;

class FaceKeyClassFactory : public IClassFactory {
public:
    FaceKeyClassFactory() : _cRef(1) {}

    // IUnknown
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) {
        static const QITAB qit[] = {
            QITABENT(FaceKeyClassFactory, IClassFactory),
            { nullptr },
        };
        return QISearch(this, qit, riid, ppv);
    }

    IFACEMETHODIMP_(ULONG) AddRef() {
        return InterlockedIncrement(&_cRef);
    }

    IFACEMETHODIMP_(ULONG) Release() {
        LONG cRef = InterlockedDecrement(&_cRef);
        if (!cRef) delete this;
        return cRef;
    }

    // IClassFactory
    IFACEMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv) {
        if (pUnkOuter) return CLASS_E_NOAGGREGATION;

        FaceKeyProvider* pProvider = new(std::nothrow) FaceKeyProvider();
        if (!pProvider) return E_OUTOFMEMORY;

        HRESULT hr = pProvider->QueryInterface(riid, ppv);
        pProvider->Release();
        return hr;
    }

    IFACEMETHODIMP LockServer(BOOL bLock) {
        if (bLock) InterlockedIncrement(&g_cRef);
        else       InterlockedDecrement(&g_cRef);
        return S_OK;
    }

private:
    ~FaceKeyClassFactory() {}
    LONG _cRef;
};

BOOL WINAPI DllMain(HINSTANCE hInstance, DWORD dwReason, LPVOID) {
    switch (dwReason) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hInstance);
        g_hInstance = hInstance;
        break;
    case DLL_PROCESS_DETACH:
        break;
    }
    return TRUE;
}

STDAPI DllCanUnloadNow() {
    return (g_cRef > 0) ? S_FALSE : S_OK;
}

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv) {
    if (!IsEqualCLSID(rclsid, CLSID_FaceKeyProvider))
        return CLASS_E_CLASSNOTAVAILABLE;

    FaceKeyClassFactory* pFactory = new(std::nothrow) FaceKeyClassFactory();
    if (!pFactory) return E_OUTOFMEMORY;

    HRESULT hr = pFactory->QueryInterface(riid, ppv);
    pFactory->Release();
    return hr;
}
