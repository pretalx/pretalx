// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

let activeElement = null
let menu = null

const getSelection = () => {
    if (!activeElement) return ""
    let start = activeElement.selectionStart
    let finish = activeElement.selectionEnd
    if (start === undefined || finish === undefined) {
        return ""
    }
    return activeElement.value.substring(start, finish)
}

const getSelectionCoords = (element) => {
    const div = document.createElement("div")
    const style = getComputedStyle(element)
    const props = [
        "fontFamily", "fontSize", "fontWeight", "fontStyle", "fontVariant",
        "letterSpacing", "wordSpacing", "textIndent", "lineHeight",
        "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
        "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
        "boxSizing", "whiteSpace", "wordWrap", "overflowWrap", "wordBreak"
    ]
    for (const prop of props) {
        div.style[prop] = style[prop]
    }
    div.style.position = "fixed"
    div.style.visibility = "hidden"
    div.style.left = "-9999px"
    div.style.top = "0"
    div.style.width = element.clientWidth + "px"
    div.style.height = "auto"
    div.style.whiteSpace = "pre-wrap"
    div.style.overflowWrap = "break-word"

    const textBefore = element.value.substring(0, element.selectionStart)
    div.textContent = textBefore
    const marker = document.createElement("span")
    marker.textContent = "\u200B"
    div.appendChild(marker)
    document.body.appendChild(div)

    const markerRect = marker.getBoundingClientRect()
    const divRect = div.getBoundingClientRect()
    const coords = {
        x: markerRect.left - divRect.left,
        y: markerRect.top - divRect.top
    }
    document.body.removeChild(div)
    return coords
}

const updateMenu = () => {
    if (!menu) {
        return
    }
    if (!activeElement) {
        menu.classList.add("d-none")
        return
    }
    let sel = getSelection()
    if (!sel) {
        menu.classList.add("d-none")
        return
    }
    menu.classList.remove("d-none")

    const button = menu.querySelector("button")
    const menuHeight = button.offsetHeight + 12
    const menuWidth = button.offsetWidth

    const elementRect = activeElement.getBoundingClientRect()
    const selCoords = getSelectionCoords(activeElement)

    const left = elementRect.left + selCoords.x - menuWidth * 0.3 + 20
    const top = elementRect.top + selCoords.y - menuHeight

    menu.style.left = Math.max(8, left) + "px"
    menu.style.top = Math.max(8, top) + "px"
}

const censor = (ev) => {
    let sel = getSelection()
    if (!sel) {
        return
    }
    let start = activeElement.selectionStart
    let value = activeElement.value
    activeElement.value =
        value.substring(0, start) +
        "█".repeat(sel.length) +
        value.substring(start + sel.length, value.length)
    activeElement = null
    updateMenu()
}

const onSelect = (ev) => {
    activeElement = ev.target
    updateMenu()
}
const triggerCensoring = () => {
    menu = document.querySelector("#anon-menu")
    menu.querySelector("button").addEventListener("click", censor)
    document
        .querySelectorAll(".anonymised input, .anonymised textarea")
        .forEach((element) => {
            element.addEventListener("keyup", onSelect)
            element.addEventListener("mouseup", onSelect)
            element.addEventListener("compositionupdate", onSelect)
            element.addEventListener("blur", onSelect)
        })
    window.addEventListener("scroll", updateMenu, true)
}
onReady(triggerCensoring)
