#pragma once
#include "common.h"

class FaceKeyCredential : public ICredentialProviderCredential {
public:
    FaceKeyCredential();

    // IUnknown
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv);
    IFACEMETHODIMP_(ULONG) AddRef();
    IFACEMETHODIMP_(ULONG) Release();

    // ICredentialProviderCredential
    IFACEMETHODIMP Advise(ICredentialProviderCredentialEvents* pcpce);
    IFACEMETHODIMP UnAdvise();
    IFACEMETHODIMP SetSelected(BOOL* pbAutoLogon);
    IFACEMETHODIMP SetDeselected();
    IFACEMETHODIMP GetFieldState(DWORD dwFieldID,
                                 CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
                                 CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis);
    IFACEMETHODIMP GetStringValue(DWORD dwFieldID, PWSTR* ppwsz);
    IFACEMETHODIMP GetBitmapValue(DWORD dwFieldID, HBITMAP* phbmp);
    IFACEMETHODIMP GetCheckboxValue(DWORD dwFieldID, BOOL* pbChecked, PWSTR* ppwszLabel);
    IFACEMETHODIMP GetSubmitButtonValue(DWORD dwFieldID, DWORD* pdwAdjacentTo);
    IFACEMETHODIMP GetComboBoxValueCount(DWORD dwFieldID, DWORD* pcItems, DWORD* pdwSelectedItem);
    IFACEMETHODIMP GetComboBoxValueAt(DWORD dwFieldID, DWORD dwItem, PWSTR* ppwszItem);
    IFACEMETHODIMP SetStringValue(DWORD dwFieldID, PCWSTR pwz);
    IFACEMETHODIMP SetCheckboxValue(DWORD dwFieldID, BOOL bChecked);
    IFACEMETHODIMP SetComboBoxSelectedValue(DWORD dwFieldID, DWORD dwSelectedItem);
    IFACEMETHODIMP CommandLinkClicked(DWORD dwFieldID);
    IFACEMETHODIMP GetSerialization(
        CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
        PWSTR* ppwszOptionalStatusText,
        CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon);
    IFACEMETHODIMP ReportResult(
        NTSTATUS ntsStatus, NTSTATUS ntsSubstatus,
        PWSTR* ppwszOptionalStatusText,
        CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon);

    void Initialize(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus);

private:
    ~FaceKeyCredential();

    void SetStatusText(PCWSTR text);
    HRESULT PackCredentials(
        PCWSTR domain, PCWSTR username, PCWSTR password,
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs);

    LONG _cRef;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _cpus;
    ICredentialProviderCredentialEvents* _pEvents;

    WCHAR _statusText[256];
    WCHAR _password[128];
    bool _faceAuthSuccess;
    std::wstring _matchedUser;
};
