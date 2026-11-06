// SPDX-License-Identifier: AGPL-3.0-or-later
// Armada's JavaScript API for CuraEngine. scripts/build.py copies this file into the engine source as
// src/armada/armada_bindings.cpp, and the patch compiles it into the Emscripten executable only.

#include <emscripten/bind.h>

#include <string>

namespace
{

std::string version()
{
    return CURA_ENGINE_VERSION;
}

} // namespace

EMSCRIPTEN_BINDINGS(armada)
{
    emscripten::function("version", &version);
}