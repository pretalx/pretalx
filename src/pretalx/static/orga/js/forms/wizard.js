// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const number = new Date().getFullYear()
const updateSlug = (ev) => {
    const value = ev.target.value
    let slug = value
        .replace(/[^a-z0-9]+/gi, "-")
        .replace(/^-|-$/g, "")
        .toLowerCase()
    if (slug && !/(?<!\d)(19|20)\d{2}(?!\d)/.test(slug)) slug += `-${number}`
    if (slug) document.querySelector("#id_basics-slug").value = slug
}
onReady(() => {
    const i18nNameInputs = document
        .getElementById("id_basics-name_0")
        .parentElement.querySelectorAll("input")
    i18nNameInputs.forEach((element) => {
        element.addEventListener("input", updateSlug)
    })
    document.querySelector("#id_basics-slug").addEventListener("input", (_ev) => {
        i18nNameInputs.forEach((element) => {
            element.removeEventListener("input", updateSlug)
        })
    })
})
