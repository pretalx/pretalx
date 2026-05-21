// SPDX-FileCopyrightText: 2022-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    const stateInput = document.querySelector("#id_state")
    if (!stateInput) return
    const updatePendingVisibility = () => {
        setBlockVisibility("#pending", !!stateInput.value)
    }
    stateInput.addEventListener("change", updatePendingVisibility)
    updatePendingVisibility()
})
