// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const fileWarningContainer = (element) => {
    const wrapper = element.closest(".file-input")
    return (wrapper && wrapper.parentElement) || element.parentElement
}
const warnFileSize = (element) => {
    unwarnFileSize(element)
    const warning = document.createElement("div")
    warning.classList = ["invalid-feedback"]
    warning.textContent = element.dataset.sizewarning
    fileWarningContainer(element).appendChild(warning)
    element.setAttribute("aria-invalid", "true")
    element.setCustomValidity(element.dataset.sizewarning)
}
const unwarnFileSize = (element) => {
    element.removeAttribute("aria-invalid")
    element.setCustomValidity("")
    const container = fileWarningContainer(element)
    const warning = container.querySelector(".invalid-feedback")
    if (warning) container.removeChild(warning)
}
const checkFileSize = (element) => {
    if (!element.dataset.maxsize) return
    const files = element.files
    const maxsize = parseInt(element.dataset.maxsize)
    if (files && files.length && files[0].size > maxsize) {
        warnFileSize(element)
    } else {
        unwarnFileSize(element)
    }
}

const showFileNames = (element) => {
    const wrapper = element.closest(".file-input")
    if (!wrapper) return
    const output = wrapper.querySelector(".file-input-filename")
    if (!output) return
    const files = element.files
    if (files && files.length) {
        const names = Array.from(files)
            .map((file) => file.name)
            .join(", ")
        output.textContent = names
        output.classList.add("has-file")
        wrapper.title = names
        const clear = wrapper.querySelector(".file-input-clear > input")
        if (clear) clear.checked = false
    } else {
        output.textContent = output.dataset.emptyText || ""
        output.classList.remove("has-file")
        wrapper.removeAttribute("title")
    }
}

const initFileInputs = () => {
    document
        .querySelectorAll(".file-input > input[type=file]")
        .forEach(showFileNames)
}

document.addEventListener("change", (event) => {
    const element = event.target
    if (element.matches(".file-input > input[type=file]")) {
        checkFileSize(element)
        showFileNames(element)
    }
    if (element.matches(".file-input-clear > input") && element.checked) {
        const input = element.closest(".file-input").querySelector("input[type=file]")
        input.value = ""
        unwarnFileSize(input)
        showFileNames(input)
    }
})
window.addEventListener("pageshow", initFileInputs)
onReady(initFileInputs)
