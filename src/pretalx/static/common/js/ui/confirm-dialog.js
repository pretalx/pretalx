// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    let pendingLoad = null
    let refocusTarget = null
    // Bumped on every dialog open and close, used to discard responses for old versions.
    let generation = 0

    const getContent = () => document.getElementById("dialog-action-confirm-content")
    const showLoading = (content) => {
        const template = document.getElementById("dialog-action-confirm-loading")
        if (template) content.replaceChildren(template.content.cloneNode(true))
    }

    const showError = (content, status) => {
        const template = document.getElementById("dialog-action-confirm-error")
        if (!template) return
        const fragment = template.content.cloneNode(true)
        const messages = Array.from(fragment.querySelectorAll("[data-error]"))
        const key = messages.some((message) => message.dataset.error === String(status))
            ? String(status)
            : "default"
        messages.forEach((message) => {
            if (message.dataset.error !== key) message.remove()
        })
        content.replaceChildren(fragment)
    }
    const onError = (event) => {
        const content = getContent()
        if (!content || event.detail?.target !== content) return
        if (event.detail.xhr?.confirmDialogGeneration !== generation) return
        showError(content, event.detail.xhr?.status)
    }
    document.body.addEventListener("htmx:responseError", onError)
    document.body.addEventListener("htmx:sendError", onError)

    document.body.addEventListener("htmx:beforeRequest", (event) => {
        if (event.detail?.target !== getContent()) return
        event.detail.xhr.confirmDialogGeneration = generation
        if (event.detail.requestConfig?.verb === "get") pendingLoad = event.detail.xhr
    })
    document.body.addEventListener("htmx:afterRequest", (event) => {
        if (event.detail?.xhr === pendingLoad) pendingLoad = null
    })
    const cancelPendingLoad = () => {
        if (pendingLoad) {
            pendingLoad.abort()
            pendingLoad = null
        }
    }

    document.body.addEventListener("htmx:beforeSwap", (event) => {
        if (event.detail?.target !== getContent()) return
        if (event.detail.xhr?.confirmDialogGeneration !== generation) {
            event.detail.shouldSwap = false
            return
        }
        if (!event.detail.xhr?.getResponseHeader("Pretalx-Dialog")) {
            event.detail.shouldSwap = false
            document.getElementById("dialog-action-confirm")?.close()
            const url =
                event.detail.xhr?.responseURL ||
                event.detail.pathInfo?.finalRequestPath
            if (url) window.location.assign(url)
        }
    })

    document.addEventListener("click", (event) => {
        // Modified clicks use native navigation, so they open in a new tab/window
        if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.ctrlKey ||
            event.metaKey ||
            event.shiftKey ||
            event.altKey
        )
            return
        const link = event.target.closest("a[data-confirm-dialog][href]")
        if (!link || typeof htmx === "undefined") return
        const dialog = document.getElementById("dialog-action-confirm")
        const dialogContent = getContent()
        if (!dialog || !dialogContent) return
        event.preventDefault()
        generation += 1
        cancelPendingLoad()
        // Close dropdowns so we don't have conflicting focus / overlay management headaches
        const dropdown = link.closest("details.dropdown")
        refocusTarget = null
        if (dropdown) {
            dropdown.open = false
            refocusTarget = dropdown.querySelector("summary")
        }
        showLoading(dialogContent)
        dialog.showModal()
        htmx.ajax("GET", link.href, {
            target: dialogContent,
            swap: "innerHTML",
            source: link,
            select: "unset",
            selectOOB: "unset",
            push: "false",
            replace: "false",
        })
    })

    document.addEventListener(
        "close",
        (event) => {
            if (event.target.id === "dialog-action-confirm") {
                generation += 1
                cancelPendingLoad()
                getContent().innerHTML = ""
                refocusTarget?.focus()
                refocusTarget = null
            }
        },
        true,
    )
})
