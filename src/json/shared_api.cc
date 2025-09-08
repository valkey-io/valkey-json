/*
 * Copyright (c) 2025, valkey-json contributors
 * All rights reserved.
 * SPDX-License-Identifier: BSD 3-Clause
 *
 */

#include "shared_api.h"
#include "json/json.h"
#include "json/dom.h"
#include "json/selector.h"

void SharedAPI_Register(ValkeyModuleCtx *ctx) {
    if(ValkeyModule_ExportSharedAPI(ctx, "JSON_GetValue", (void *)SharedJSON_Get) != VALKEYMODULE_OK) {
        ValkeyModule_Assert(false);
    }
}

int SharedJSON_Get(ValkeyModuleKey *key, const char *path, ValkeyModuleString **result) {
    if (verify_open_doc_key(key) != JSONUTIL_SUCCESS) {
        return VALKEYMODULE_ERR;
    }
    // Fetch the document from the key
    JDocument *doc = static_cast<JDocument *>(ValkeyModule_ModuleTypeGetValue(key));
    rapidjson::StringBuffer output;
    if (dom_get_value_as_str(doc, path, nullptr, output) == JSONUTIL_SUCCESS) {
        *result = ValkeyModule_CreateString(nullptr, output.GetString(), output.GetLength());
        return VALKEYMODULE_OK;
    } else {
        return VALKEYMODULE_ERR;
    }
}

