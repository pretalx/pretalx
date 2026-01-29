// SPDX-FileCopyrightText: 2025-present Florian Moesch
// SPDX-License-Identifier: Apache-2.0

function initStarRating(root) {
    const stars = Array.from(root.querySelectorAll(".star"));
    const hiddenInput = root.querySelector("input[type=hidden]");
    let currentValue = Number(hiddenInput.value || 0);
    
    function render(value) {
        stars.forEach((star) => {
            const starValue = Number(star.dataset.value);
            star.classList.toggle("color-active", starValue <= value);
        });
    }
    
    render(currentValue);
    
    stars.forEach((star) => {
        star.addEventListener("mouseenter", () => {
            render(Number(star.dataset.value));
        });
        star.addEventListener("mouseleave", () => {
            render(currentValue);
        });
        star.addEventListener("click", () => {
            currentValue = Number(star.dataset.value);
            hiddenInput.value = String(currentValue);
            render(currentValue);
        });
    });
    
    function syncAria() {
        root.setAttribute("aria-valuenow", String(currentValue));
    }
    root.addEventListener("click", syncAria);
    root.addEventListener("keydown", syncAria);
}

// onReady(() =>
document.addEventListener("DOMContentLoaded", () => {
    document
    .querySelectorAll(".star-rating")
    .forEach((element) => initStarRating(element))
})
