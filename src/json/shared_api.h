/*
 * Copyright (c) 2025, valkey-json contributors
 * All rights reserved.
 * SPDX-License-Identifier: BSD 3-Clause
 *
 */

#ifndef VALKEYJSONMODULE_SHARED_API_H_
#define VALKEYJSONMODULE_SHARED_API_H_

#include "./include/valkeymodule.h"

#include <stddef.h>

//
// Fetch JSON text associated with "path".
//
// Errors:
//
//   If the key isn't JSON, then you'll get REDISMODULE_ERR for the return.
//   If the key is JSON, but the path doesn't identify anything, then you'll get a nullptr for the result.
//   Otherwise you get the JSON text that matches the path.
//
int SharedJSON_Get(ValkeyModuleKey *key, const char *path, ValkeyModuleString **result);

//
// Internal.
//
void SharedAPI_Register(ValkeyModuleCtx *ctx);


#endif  // VALKEYJSONMODULE_SHARED_API_H_
