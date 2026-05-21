// SPDX-FileCopyrightText: 2021-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const smtpInput = document.querySelector("input#id_smtp_use_custom")
const smtpSettings = document.querySelector("#smtp-settings")
const updateVisibility = () => {
    const showCustomSettings = smtpInput.checked
    setBlockVisibility(smtpSettings, showCustomSettings)
    document.querySelector("button[name=test]").disabled = !showCustomSettings
}
onReady(() => {
    smtpInput.addEventListener("change", updateVisibility)
    updateVisibility()
})
