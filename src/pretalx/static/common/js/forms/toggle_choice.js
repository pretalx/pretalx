// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Use event delegation so it works for dynamically added content (e.g., after htmx swap)
document.addEventListener("click", (event) => {
  const button = event.target.closest(".toggle-choice-btn")
  if (!button) return

  const wrapper = button.closest(".toggle-choice-wrapper")
  const input = wrapper.querySelector(".toggle-choice-input")
  const choices = JSON.parse(button.dataset.choices)
  const values = JSON.parse(button.dataset.values)

  const currentValue = input.value.trim()
  let currentIndex = values.indexOf(currentValue)
  if (currentIndex === -1) currentIndex = 0

  const newIndex = currentIndex === 0 ? 1 : 0
  const newValue = values[newIndex]

  input.value = newValue
  const icon = button.querySelector("i")
  button.textContent = " " + choices[newValue]
  if (icon) button.prepend(icon)
  button.setAttribute("aria-pressed", newIndex === 1 ? "true" : "false")
})
