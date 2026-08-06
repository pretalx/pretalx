// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const buildAvatar = (item) => {
    if (!item || !item.customProperties || !item.customProperties.avatar) {
        return null
    }
    const avatar = document.createElement("img")
    avatar.src = item.customProperties.avatar
    avatar.alt = ""
    avatar.loading = "lazy"
    avatar.className = "choice-item-avatar"
    avatar.addEventListener("error", () => avatar.remove())
    return avatar
}

const initSpeakerSearch = (select) => {
    const remoteURL = select.getAttribute("data-remote-url")
    const existingSelectable =
        select.getAttribute("data-existing-selectable") !== "false"
    const existingNote = select.getAttribute("data-existing-note")
    const form = select.closest("form")
    const scope = form || document
    const details = scope.querySelector(".add-speaker-details")
    const nameWrapper = scope.querySelector(".add-speaker-name")
    const emailLessBlock = scope.querySelector(".add-speaker-email-less")
    const inviteBlock = scope.querySelector(".add-speaker-invite")
    const inviteTextBlock = scope.querySelector(".add-speaker-invite-text")
    const nameInput =
        scope.querySelector("#id_name") || scope.querySelector("#id_speaker-name")
    const emailInput =
        scope.querySelector("#id_email") || scope.querySelector("#id_speaker-email")
    const inviteCheckbox =
        scope.querySelector("#id_send_invite") ||
        scope.querySelector("#id_speaker-send_invite")
    const inviteDefault = inviteCheckbox ? inviteCheckbox.checked : false
    const localeSelect =
        scope.querySelector("#id_locale") ||
        scope.querySelector("#id_speaker-locale")
    const templateData =
        scope.querySelector("#speaker-invite-templates") ||
        document.getElementById("speaker-invite-templates")
    const subjectInput =
        scope.querySelector("#id_invite_subject") ||
        scope.querySelector("#id_speaker-invite_subject")
    const textInput =
        scope.querySelector("#id_invite_text") ||
        scope.querySelector("#id_speaker-invite_text")
    const inviteVariants = templateData
        ? JSON.parse(templateData.textContent)
        : null
    let inviteTextReady = false
    let lastInviteKey = null

    if (nameWrapper) nameWrapper.classList.add("d-none")

    let selectedProps = null
    let currentMode = null

    const classify = () => {
        const value = select.value
        const emailEntered = Boolean(emailInput && emailInput.value.trim())
        if (value) {
            if (value.startsWith("profile:")) {
                return { mode: "profile", props: selectedProps }
            }
            return { mode: emailEntered ? "email" : "name" }
        }
        if (emailEntered) return { mode: "email" }
        const typed =
            (searchInput && searchInput.value.trim()) ||
            (nameInput && nameInput.value.trim())
        if (typed) return { mode: "name" }
        return { mode: "empty" }
    }

    const updateInviteText = () => {
        if (!inviteTextBlock) return
        const inviteVisible =
            inviteBlock && !inviteBlock.classList.contains("d-none")
        const visible =
            inviteTextBlock.hasAttribute("data-expanded") ||
            Boolean(inviteVisible && inviteCheckbox && inviteCheckbox.checked)
        inviteTextBlock.classList.toggle("d-none", !visible)
    }

    const currentName = () => {
        const picked = nameInput ? nameInput.value.trim() : ""
        if (picked) return picked
        const typed = searchInput ? searchInput.value.trim() : ""
        return typed.includes("@") ? "" : typed
    }

    const inviteKey = () =>
        `${localeSelect ? localeSelect.value : ""} ${currentName()}`

    const refreshInviteText = () => {
        if (!inviteTextReady || !inviteVariants || !subjectInput || !textInput) {
            return
        }
        const key = inviteKey()
        if (key === lastInviteKey) return
        lastInviteKey = key
        let variant = localeSelect ? inviteVariants[localeSelect.value] : null
        if (!variant) {
            const locales = Object.keys(inviteVariants)
            if (!locales.length) return
            variant = inviteVariants[locales[0]]
        }
        const name = currentName()
        const literalName = name.replaceAll("{", "{{").replaceAll("}", "}}")
        const apply = (value) =>
            name ? value.split("{name}").join(literalName) : value
        subjectInput.value = apply(variant.subject)
        textInput.value = apply(variant.text)
    }

    const updateVisibility = () => {
        const { mode, props } = classify()
        if (details) {
            let detailsVisible
            if (select.value) {
                detailsVisible = mode !== "profile"
            } else {
                detailsVisible =
                    details.hasAttribute("data-expanded") || mode !== "empty"
            }
            details.classList.toggle("d-none", !detailsVisible)
        }
        if (emailLessBlock) {
            if (currentMode !== null && mode !== currentMode) {
                emailLessBlock.removeAttribute("data-expanded")
            }
            const emailLessVisible =
                mode === "name" || emailLessBlock.hasAttribute("data-expanded")
            emailLessBlock.classList.toggle("d-none", !emailLessVisible)
        }
        if (inviteBlock) {
            let inviteVisible = false
            if (mode === "profile") {
                inviteVisible = Boolean(props && props.managed && props.has_email)
            } else if (mode === "email") {
                inviteVisible = true
            }
            if (currentMode !== null && mode !== currentMode) {
                inviteBlock.removeAttribute("data-expanded")
            }
            inviteVisible =
                inviteVisible || inviteBlock.hasAttribute("data-expanded")
            inviteBlock.classList.toggle("d-none", !inviteVisible)
            if (currentMode !== null && mode !== currentMode && inviteCheckbox) {
                if (mode === "profile") {
                    inviteCheckbox.checked = false
                } else if (inviteVisible) {
                    inviteCheckbox.checked = inviteDefault
                }
            }
        }
        currentMode = mode
        updateInviteText()
        refreshInviteText()
    }

    const choices = new Choices(select, {
        maxItemCount: 1,
        singleModeForMultiSelect: true,
        closeDropdownOnSelect: true,
        addChoices: true,
        removeItems: true,
        removeItemButton: true,
        removeItemButtonAlignLeft: true,
        searchEnabled: true,
        searchFloor: 3,
        searchResultLimit: -1,
        shouldSort: false,
        placeholder: true,
        placeholderValue: select.getAttribute("placeholder"),
        itemSelectText: "",
        noResultsText: "",
        noChoicesText: "",
        addItemText: "",
        removeItemLabelText: "×",
        removeItemIconText: "×",
        maxItemText: "",
        callbackOnCreateTemplates: () => ({
            choice: (...args) => {
                const element = Choices.defaults.templates.choice(...args)
                const item = args[1]
                const avatar = buildAvatar(item)
                if (avatar) element.prepend(avatar)
                if (item && item.customProperties && item.customProperties.note) {
                    const note = document.createElement("span")
                    note.textContent = item.customProperties.note
                    note.className = "choice-item-note"
                    element.append(note)
                }
                if (
                    item &&
                    item.customProperties &&
                    item.customProperties.unselectable
                ) {
                    element.classList.add("choices__item--disabled")
                }
                return element
            },
            item: (...args) => {
                const element = Choices.defaults.templates.item(...args)
                const item = args[1]
                const avatar = buildAvatar(item)
                if (avatar) {
                    const button = element.querySelector("button")
                    if (button && button.nextSibling) {
                        element.insertBefore(avatar, button.nextSibling)
                    } else {
                        element.prepend(avatar)
                    }
                }
                return element
            },
        }),
    })
    const searchInput = select.parentElement.parentElement.querySelector("input")

    const serializeEntry = (item) => {
        const entry = {
            value: `profile:${item.code}`,
            label: item.name,
            customProperties: {
                type: "profile",
                name: item.name,
                avatar: item.avatar,
                managed: item.managed,
                has_email: item.has_email,
            },
        }
        if (!existingSelectable) {
            entry.customProperties.unselectable = true
            entry.customProperties.note = existingNote
        }
        return entry
    }
    select.addEventListener("search", (ev) => {
        fetch(`${remoteURL}?search=${encodeURIComponent(ev.detail.value)}`)
            .then((r) => r.json())
            .then((data) => {
                choices.setChoices(
                    data.results.map((group) => ({
                        label: group.label,
                        choices: group.entries.map(serializeEntry),
                    })),
                    "value",
                    "label",
                    true,
                )
            })
    })
    select.addEventListener("addItem", (ev) => {
        if (ev.detail.customProperties && ev.detail.customProperties.unselectable) {
            setTimeout(() => {
                choices.removeActiveItems()
                updateVisibility()
            }, 0)
            return
        }
        const value = ev.detail.value || ""
        if (
            !ev.detail.customProperties &&
            value.includes("@") &&
            !value.startsWith("profile:")
        ) {
            setTimeout(() => {
                choices.removeActiveItems()
                if (emailInput) emailInput.value = value
                updateVisibility()
            }, 0)
            return
        }
        selectedProps = ev.detail.customProperties || null
        if (nameInput) {
            if (selectedProps && selectedProps.name) {
                nameInput.value = selectedProps.name
            } else if (
                value &&
                !value.startsWith("profile:") &&
                !value.includes("@")
            ) {
                nameInput.value = value
            }
        }
        updateVisibility()
    })
    select.addEventListener("removeItem", () => {
        selectedProps = null
        if (nameInput) nameInput.value = ""
        updateVisibility()
    })
    if (searchInput) {
        searchInput.addEventListener("input", () => updateVisibility())
        searchInput.addEventListener("blur", (ev) => {
            const unfinishedInput = ev.target.value.trim()
            if (!unfinishedInput) {
                updateVisibility()
                return
            }
            if (!select.value) {
                if (unfinishedInput.includes("@")) {
                    if (emailInput) emailInput.value = unfinishedInput
                } else {
                    choices.setChoices(
                        [
                            {
                                value: unfinishedInput,
                                label: unfinishedInput,
                                selected: true,
                            },
                        ],
                        "value",
                        "label",
                        true,
                    )
                }
                choices.clearInput()
            }
            updateVisibility()
        })
    }
    if (emailInput) {
        emailInput.addEventListener("input", () => updateVisibility())
    }
    if (inviteCheckbox) {
        inviteCheckbox.addEventListener("change", () => {
            if (inviteTextBlock) inviteTextBlock.removeAttribute("data-expanded")
            updateInviteText()
        })
    }
    if (form) {
        form.addEventListener("submit", () => {
            const value = select.value
            if (value && !value.startsWith("profile:") && !value.includes("@")) {
                if (nameInput) nameInput.value = value
                select
                    .querySelectorAll("option")
                    .forEach((option) => option.remove())
            } else if (!value && searchInput) {
                const typed = searchInput.value.trim()
                if (typed.includes("@")) {
                    if (emailInput && !emailInput.value.trim()) {
                        emailInput.value = typed
                    }
                } else if (typed && nameInput) {
                    nameInput.value = typed
                }
            }
        })
    }

    if (localeSelect) {
        localeSelect.addEventListener("change", () => refreshInviteText())
    }

    const initialValue = select.value
    const initialName = nameInput ? nameInput.value.trim() : ""
    if (initialValue && !initialValue.startsWith("profile:")) {
        choices.removeActiveItems()
        if (initialName) {
            choices.setChoices(
                [
                    {
                        value: initialValue,
                        label: initialName,
                        selected: true,
                    },
                ],
                "value",
                "label",
                true,
            )
        } else if (
            initialValue.includes("@") &&
            emailInput &&
            !emailInput.value.trim()
        ) {
            emailInput.value = initialValue
        }
    } else if (initialValue && initialName) {
        choices.removeActiveItems()
        choices.setChoices(
            [
                {
                    value: initialValue,
                    label: initialName,
                    selected: true,
                    customProperties: { type: "profile", name: initialName },
                },
            ],
            "value",
            "label",
            true,
        )
    } else if (initialName && !initialValue) {
        choices.setChoices(
            [
                {
                    value: initialName,
                    label: initialName,
                    selected: true,
                },
            ],
            "value",
            "label",
            true,
        )
    }
    updateVisibility()
    lastInviteKey = inviteKey()
    inviteTextReady = true
}
document
    .querySelectorAll("select[data-remote-url]")
    .forEach((select) => initSpeakerSearch(select))
