// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const warnFileSize = (element) => {
    const warning = document.createElement("div")
    warning.classList = ["invalid-feedback"]
    warning.textContent = element.dataset.sizewarning
    element.parentElement.appendChild(warning)
    element.classList.add("is-invalid")
}
const unwarnFileSize = (element) => {
    element.classList.remove("is-invalid")
    const warning = element.parentElement.querySelector(".invalid-feedback")
    if (warning) element.parentElement.removeChild(warning)
}

const initFileSizeCheck = (element) => {
    const checkFileSize = () => {
        const files = element.files
        if (!files || !files.length) {
            unwarnFileSize(element)
        } else {
            maxsize = parseInt(element.dataset.maxsize)
            if (files[0].size > maxsize) {
                warnFileSize(element)
            } else {
                unwarnFileSize(element)
            }
        }
    }
    element.addEventListener("change", checkFileSize, false)
}

onReady(() => {
    document
        .querySelectorAll("input[data-maxsize][type=file]")
        .forEach((element) => initFileSizeCheck(element))
})
