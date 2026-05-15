// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const LIGHT_BG = [255, 255, 255]
const DARK_BG = [18, 20, 22] // #121416
const CONTRAST_THRESHOLD = 2.5

const channelLuminance = (v) => {
    v /= 255
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
}

const relativeLuminance = (r, g, b) =>
    0.2126 * channelLuminance(r) +
    0.7152 * channelLuminance(g) +
    0.0722 * channelLuminance(b)

const contrastRatio = (rgb1, rgb2) => {
    const l1 = relativeLuminance(rgb1[0], rgb1[1], rgb1[2]) + 0.05
    const l2 = relativeLuminance(rgb2[0], rgb2[1], rgb2[2]) + 0.05
    const ratio = l1 > l2 ? l1 / l2 : l2 / l1
    return Number(ratio.toFixed(1))
}

// Match has_good_contrast(threshold=3) / primary_color_needs_dark_text in the
// backend.
const ON_PRIMARY_LIGHT = "#fff"
const ON_PRIMARY_DARK = "rgb(13, 15, 16)"
const textOnPrimary = (rgb) =>
    1.05 / (relativeLuminance(rgb[0], rgb[1], rgb[2]) + 0.05) >= 3
        ? ON_PRIMARY_LIGHT
        : ON_PRIMARY_DARK

const contrastState = (rgb) => {
    const onLight = contrastRatio(LIGHT_BG, rgb) >= CONTRAST_THRESHOLD
    const onDark = contrastRatio(DARK_BG, rgb) >= CONTRAST_THRESHOLD
    if (onLight && onDark) return "good"
    if (onLight) return "lightOnly"
    if (onDark) return "darkOnly"
    return "bad"
}

const STATE_META = {
    good: {
        key: "contrastGood",
        icon: "fa-check-circle",
        css: "text-success",
        tint: "good",
    },
    lightOnly: {
        key: "contrastLightOnly",
        icon: "fa-info-circle",
        css: "text-warning",
        tint: "warning",
    },
    darkOnly: {
        key: "contrastDarkOnly",
        icon: "fa-info-circle",
        css: "text-warning",
        tint: "warning",
    },
    bad: {
        key: "contrastBad",
        icon: "fa-warning",
        css: "text-danger",
        tint: "danger",
    },
}

// h, s, l in [0, 1]; returns [r, g, b] in [0, 255].
const hslToRgb = (h, s, l) => {
    if (s === 0) {
        const v = Math.round(l * 255)
        return [v, v, v]
    }
    const hue2rgb = (p, q, t) => {
        if (t < 0) t += 1
        if (t > 1) t -= 1
        if (t < 1 / 6) return p + (q - p) * 6 * t
        if (t < 1 / 2) return q
        if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
        return p
    }
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s
    const p = 2 * l - q
    return [
        Math.round(hue2rgb(p, q, h + 1 / 3) * 255),
        Math.round(hue2rgb(p, q, h) * 255),
        Math.round(hue2rgb(p, q, h - 1 / 3) * 255),
    ]
}

// Match default text colour that mixes in 10% black/white.
const channelHex = (n) =>
    Math.round(Math.min(255, Math.max(0, n)))
        .toString(16)
        .padStart(2, "0")

const mixSrgb = (rgb, target, amount) =>
    "#" +
    rgb
        .map((c, i) => channelHex(c * (1 - amount) + target[i] * amount))
        .join("")

const hexToRgb = (hex) => {
    const h = hex.replace(/^#/, "")
    return [
        parseInt(h.slice(0, 2), 16),
        parseInt(h.slice(2, 4), 16),
        parseInt(h.slice(4, 6), 16),
    ]
}

const drawEndorsedOverlay = (slEl, hue) => {
    let canvas = slEl.querySelector(".colorpicker-endorsed-overlay")
    if (!canvas) {
        canvas = document.createElement("canvas")
        canvas.classList.add("colorpicker-endorsed-overlay")
        // Insert before the selector knob so the knob keeps painting on top.
        slEl.insertBefore(canvas, slEl.firstChild)
    }
    const width = slEl.clientWidth
    const height = slEl.clientHeight
    if (!width || !height) return
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext("2d")
    const image = ctx.createImageData(width, height)
    const data = image.data
    for (let y = 0; y < height; y++) {
        // vanilla-picker's SL square: x = saturation 0..1, y = lightness 1..0.
        const l = 1 - y / (height - 1)
        for (let x = 0; x < width; x++) {
            const s = x / (width - 1)
            const idx = (y * width + x) * 4
            if (contrastState(hslToRgb(hue, s, l)) === "good") {
                data[idx + 3] = 0 // fully transparent for good colours
            } else {
                data[idx] = 18
                data[idx + 1] = 20
                data[idx + 2] = 22
                // Dim less suitable colours so they stay visible.
                data[idx + 3] = 80
            }
        }
    }
    ctx.putImageData(image, 0, 0)
}

const updateContrast = (field, rgb, hex) => {
    field.value = hex.slice(0, 7)
    const wrapper = field.parentNode.parentNode
    wrapper.querySelector(".colorpicker-preview").style.backgroundColor = hex
    const lightText = mixSrgb(rgb, [0, 0, 0], 0.1)
    const darkText = mixSrgb(rgb, [255, 255, 255], 0.1)
    wrapper.querySelectorAll(".colorpicker-sample").forEach((sample) => {
        if (sample.classList.contains("colorpicker-sample-plain")) {
            sample.style.backgroundColor = hex
            const plainChip = sample.querySelector(".colorpicker-sample-chip")
            if (plainChip) plainChip.style.color = textOnPrimary(rgb)
            return
        }
        const chip = sample.querySelector(".colorpicker-sample-chip")
        if (!chip) return
        chip.style.color = sample.classList.contains("colorpicker-sample-dark")
            ? darkText
            : lightText
    })

    const state = contrastState(rgb)
    const meta = STATE_META[state]

    wrapper.classList.remove(
        "contrast-good",
        "contrast-warning",
        "contrast-danger",
    )
    wrapper.classList.add(`contrast-${meta.tint}`)

    if (!wrapper.querySelector(".contrast-state")) {
        const note = document.createElement("div")
        note.classList.add("help-block", "contrast-state")
        wrapper.appendChild(note)
    }
    const note = wrapper.querySelector(".contrast-state")
    note.classList.remove("text-success", "text-warning", "text-danger")
    note.classList.add(meta.css)
    note.innerHTML = `<span class='fa fa-fw ${meta.icon}'></span> ${field.dataset[meta.key]}`
}

const buildSamples = () => {
    const samples = document.createElement("div")
    samples.classList.add("colorpicker-samples")
    for (const mode of ["plain", "light", "dark"]) {
        const sample = document.createElement("span")
        sample.classList.add("colorpicker-sample", `colorpicker-sample-${mode}`)
        const chip = document.createElement("span")
        chip.classList.add("colorpicker-sample-chip")
        chip.textContent = "Aa"
        sample.appendChild(chip)
        samples.appendChild(sample)
    }
    return samples
}

const initColorPicker = (field) => {
    // We're creating a parent element to hold the colorpicker/preview and the input field
    const parentEl = document.createElement("div")
    parentEl.classList.add("colorpicker-wrapper", "input-group")
    const pickerEl = document.createElement("div")
    pickerEl.classList.add("input-group-prepend")
    const wrapperEl = document.createElement("div")
    wrapperEl.classList.add("input-group-text")
    const previewEl = document.createElement("div")
    previewEl.classList.add("colorpicker-preview")
    previewEl.style.backgroundColor = field.value

    wrapperEl.appendChild(previewEl)
    pickerEl.appendChild(wrapperEl)
    parentEl.appendChild(pickerEl)
    const fieldParent = field.parentNode
    fieldParent.replaceChild(parentEl, field)
    parentEl.appendChild(field)
    parentEl.appendChild(buildSamples())

    let lastHue = null
    const redrawOverlay = (hue) => {
        const slEl = pickerEl.querySelector(".picker_sl")
        if (!slEl) return
        if (lastHue !== null && Math.abs(hue - lastHue) < 0.001) return
        lastHue = hue
        requestAnimationFrame(() => drawEndorsedOverlay(slEl, hue))
    }

    const picker = new Picker({
        parent: pickerEl,
        color: field.value,
        popup: "left",
        alpha: false,
        editor: false,
        onOpen: (color) => {
            const wrap = pickerEl.querySelector(".picker_wrapper")
            if (wrap && !wrap.querySelector(".colorpicker-samples")) {
                const popupSamples = buildSamples()
                const sampleEl = wrap.querySelector(".picker_sample")
                if (sampleEl) sampleEl.after(popupSamples)
                else wrap.appendChild(popupSamples)
                updateContrast(field, color.rgba.slice(0, 3), color.hex)
            }
            lastHue = null
            redrawOverlay(color.hsla[0])
        },
        onChange: (color) => {
            updateContrast(field, color.rgba.slice(0, 3), color.hex)
            redrawOverlay(color.hsla[0])
        },
    })

    field.addEventListener("focus", () => {
        picker.openHandler()
    })
    previewEl.addEventListener("click", () => {
        picker.openHandler()
    })

    field.addEventListener("input", () => {
        const value = field.value.replace(/^#/, "")
        if (/^[0-9a-fA-F]{6}$/.test(value)) {
            picker.setColor(field.value)
        }
    })

    // Reflect the initial value before the picker is ever opened.
    if (/^#?[0-9a-fA-F]{6}$/.test(field.value.replace(/^#/, ""))) {
        updateContrast(field, hexToRgb(field.value), field.value)
    }
}

onReady(() => {
    document.querySelectorAll("input.colorpicker").forEach((field) => {
        initColorPicker(field)
    })
})
