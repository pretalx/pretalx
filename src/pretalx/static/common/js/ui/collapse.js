// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const makeCollapsed = (controller, element, collapsed) => {
    if (controller) controller.setAttribute('aria-expanded', !collapsed)
    element.setAttribute('aria-hidden', collapsed)
    if (collapsed) {
        element.classList.remove('show')
    } else {
        element.classList.add('show')
    }
}

// .collapse.show has a height cap of 100vh so that the opening/closing animation
// is reliable and constant. We add .collapse-stable if the animation is not
// running to remove the cap.
const watchCollapseHeight = (element) => {
    let shown = element.classList.contains('show')
    if (shown) element.classList.add('collapse-stable')

    element.addEventListener('transitionend', (event) => {
        if (event.target !== element || event.propertyName !== 'max-height') return
        if (element.classList.contains('show')) element.classList.add('collapse-stable')
    })

    new MutationObserver(() => {
        const nowShown = element.classList.contains('show')
        if (nowShown === shown) return
        shown = nowShown
        if (!nowShown && element.classList.contains('collapse-stable')) {
            element.style.maxHeight = `${element.scrollHeight}px`
            void element.offsetHeight // force reflow so the height change animates
            element.classList.remove('collapse-stable')
            element.style.maxHeight = ''
        }
    }).observe(element, { attributes: true, attributeFilter: ['class'] })
}


const handleCollapse = (controller, target) => {
    const wasVisible = controller.getAttribute('aria-expanded') === 'true'
    const accordion = target.getAttribute('data-parent')
    if (accordion) {
        document.querySelectorAll(`[data-parent="${accordion}"]`).forEach(element => {
            makeCollapsed(document.querySelector(`[data-target="#${element.id}"]`), element, true)
        })
    }
    makeCollapsed(controller, target, wasVisible)
}

const setupCollapse = (element) => {
    const target = document.querySelector(element.getAttribute('data-target'))
    if (!target) return
    element.addEventListener('click', () => handleCollapse(element, target))
    if (target.classList.contains('show')) {
        makeCollapsed(element, target, false)
    }
}

const revealCollapseFor = (element) => {
    let target = element.closest('.collapse')
    while (target) {
        if (!target.classList.contains('show')) {
            const controller = target.id && document.querySelector(`[data-toggle="collapse"][data-target="#${target.id}"]`)
            if (controller) {
                handleCollapse(controller, target)
            } else {
                makeCollapsed(null, target, false)
            }
        }
        target = target.parentElement && target.parentElement.closest('.collapse')
    }
}

const initCollapse = () => {
    document.querySelectorAll('[data-toggle="collapse"]').forEach(element => {
        setupCollapse(element)
    })
    document.querySelectorAll('.collapse').forEach(watchCollapseHeight)
    registerFieldRevealHook(revealCollapseFor)
}
onReady(initCollapse)
