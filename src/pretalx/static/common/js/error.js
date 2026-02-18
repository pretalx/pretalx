// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const goback = document.getElementById("goback")
const reload = document.getElementById("reload")
if (goback) goback.onclick = () => window.history.back()
if (reload) reload.onclick = () => window.location.reload(true)
