// SPDX-FileCopyrightText: 2023-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Add a lightbox to images and links with data-lightbox attribute.
// Currently loaded on every pretalx page

const setupLightbox = () => {
    const dialog = document.querySelector("dialog#lightbox-dialog")
    const img = dialog.querySelector("img")
    const caption = dialog.querySelector("figcaption")
    if (!dialog || !img) return

    // Fallback for browsers without `closedby="any"` (Safari as of 2026, TODO 2027 check if we can drop this):
    // close on outside click, but not when clicking inside (e.g. following a link, right-click).
    if (!("closedBy" in HTMLDialogElement.prototype)) {
        dialog.addEventListener("click", () => dialog.close())
        dialog.querySelector(".modal-card-content").addEventListener("click", (ev) => ev.stopPropagation())
    }
    dialog.querySelector("button.dialog-close").addEventListener("click", () => dialog.close())

    document
        .querySelectorAll("a[data-lightbox], img[data-lightbox]")
        .forEach((element) => {
            element.addEventListener("click", function (ev) {
                const image = element.tag === "A" ? element.querySelector("img") : element
                const imageUrl = element.dataset.lightbox || element.href || image.src
                const label = image.alt
                if (!imageUrl) return
                ev.preventDefault()
                img.src = imageUrl
                caption.textContent = label || ""
                dialog.showModal()
            })
        })
}

onReady(setupLightbox)
