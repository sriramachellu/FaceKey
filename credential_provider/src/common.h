#pragma once

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <credentialprovider.h>
#include <ntsecapi.h>
#include <wincred.h>
#include <shlguid.h>
#include <strsafe.h>

#include "guid.h"

// Credential tile field IDs
enum FIELD_ID {
    FI_ICON          = 0,
    FI_LABEL         = 1,
    FI_STATUS        = 2,
    FI_PASSWORD      = 3,
    FI_SUBMIT_BUTTON = 4,
    FI_NUM_FIELDS    = 5,
};

// Field descriptors for the credential tile
static const CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR s_FieldDescriptors[] = {
    { FI_ICON,          CPFT_TILE_IMAGE,    L"Icon",     CPFG_CREDENTIAL_PROVIDER_LOGO },
    { FI_LABEL,         CPFT_LARGE_TEXT,     L"FaceKey",  CPFG_CREDENTIAL_PROVIDER_LABEL },
    { FI_STATUS,        CPFT_SMALL_TEXT,     L"Status",   GUID_NULL },
    { FI_PASSWORD,      CPFT_PASSWORD_TEXT,  L"Password", GUID_NULL },
    { FI_SUBMIT_BUTTON, CPFT_SUBMIT_BUTTON,  L"Submit",   GUID_NULL },
};

static const FIELD_STATE_PAIR s_FieldStatePairsUnlock[] = {
    { CPFS_DISPLAY_IN_SELECTED_TILE, CPFIS_NONE       },  // icon
    { CPFS_DISPLAY_IN_BOTH,          CPFIS_NONE       },  // label
    { CPFS_DISPLAY_IN_SELECTED_TILE, CPFIS_NONE       },  // status
    { CPFS_HIDDEN,                   CPFIS_NONE       },  // password (hidden during face auth)
    { CPFS_HIDDEN,                   CPFIS_NONE       },  // submit (hidden during face auth)
};

static const FIELD_STATE_PAIR s_FieldStatePairsLogon[] = {
    { CPFS_DISPLAY_IN_SELECTED_TILE, CPFIS_NONE       },  // icon
    { CPFS_DISPLAY_IN_BOTH,          CPFIS_NONE       },  // label
    { CPFS_DISPLAY_IN_SELECTED_TILE, CPFIS_NONE       },  // status
    { CPFS_DISPLAY_IN_SELECTED_TILE, CPFIS_FOCUSED    },  // password
    { CPFS_DISPLAY_IN_SELECTED_TILE, CPFIS_NONE       },  // submit
};

// Named pipe
#define FACEKEY_PIPE_NAME L"\\\\.\\pipe\\FaceKey"
#define PIPE_BUFFER_SIZE 4096
