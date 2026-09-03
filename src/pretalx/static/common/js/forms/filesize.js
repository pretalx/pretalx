// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const warnFileSize = (element) => {
    unwarnFileSize(element)
    const warning = document.createElement("div")
    warning.classList = ["invalid-feedback"]
    warning.textContent = element.dataset.sizewarning
    element.parentElement.appendChild(warning)
    element.setAttribute("aria-invalid", "true")
    element.setCustomValidity(element.dataset.sizewarning)
}
const unwarnFileSize = (element) => {
    element.removeAttribute("aria-invalid")
    element.setCustomValidity("")
    const warning = element.parentElement.querySelector(".invalid-feedback")
    if (warning) element.parentElement.removeChild(warning)
}

const checkFileSize = (element) => {
    const files = element.files
    const maxsize = parseInt(element.dataset.maxsize)
    if (files && files.length && files[0].size > maxsize) {
        warnFileSize(element)
    } else {
        unwarnFileSize(element)
    }
}

document.addEventListener("change", (event) => {
    const element = event.target
    if (element.matches("input[data-maxsize][type=file]")) checkFileSize(element)
})
