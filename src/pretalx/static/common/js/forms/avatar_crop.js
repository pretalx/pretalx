// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

let currentCropper = null
const croppedBlobs = new Map()

const initAvatarCrop = () => {
    document.querySelectorAll('.avatar-crop-widget').forEach(widget => {
        const widgetId = widget.dataset.widgetId
        const fileInput = widget.querySelector('.avatar-file-input')
        const modal = widget.querySelector('.avatar-crop-modal')
        const cropImage = widget.querySelector('.avatar-crop-image')
        const applyBtn = widget.querySelector('.avatar-crop-apply')
        const cancelBtn = widget.querySelector('.avatar-crop-cancel')

        if (!fileInput || !modal) return

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0]
            if (!file) return

            if (!file.type.startsWith('image/')) {
                alert('Please select an image file.')
                fileInput.value = ''
                return
            }

            const reader = new FileReader()
            reader.onload = (event) => {
                cropImage.src = event.target.result
                modal.showModal()
                initCropper(cropImage, modal)
            }
            reader.readAsDataURL(file)
        })

        applyBtn.addEventListener('click', () => {
            if (!currentCropper) return

            const applyBtnText = applyBtn.textContent
            applyBtn.innerHTML = `<i class="fa fa-cog animate-spin pr-0"></i> ${applyBtnText}`
            applyBtn.classList.add('disabled')

            const canvas = currentCropper.getCroppedCanvas({
                width: 1024,
                height: 1024,
                imageSmoothingEnabled: true,
                imageSmoothingQuality: 'high',
            })

            canvas.toBlob((blob) => {
                croppedBlobs.set(widgetId, blob)

                // Also get data URL for preview (CSP-safe)
                const previewUrl = canvas.toDataURL('image/webp', 0.95)

                const avatarForm = widget.closest('.avatar-form')
                const preview = avatarForm?.querySelector('.form-image-preview')
                const previewImg = preview?.querySelector('img.avatar')

                if (previewImg) {
                    previewImg.src = previewUrl
                    const previewLink = preview?.querySelector('a')
                    if (previewLink) {
                        previewLink.href = previewUrl
                        previewLink.dataset.lightbox = previewUrl
                    }
                    if (preview.classList.contains('d-none')) {
                        preview.classList.remove('d-none')
                    }
                }

                applyBtn.innerHTML = applyBtnText
                applyBtn.classList.remove('disabled')

                modal.close()
            }, 'image/webp', 0.95)
        })

        modal.querySelectorAll('.close-dialog').forEach(btn => {
            btn.addEventListener('click', () => modal.close())
        })
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.close()
        })
        modal.querySelector('.modal-card-content').addEventListener('click', (e) => {
            e.stopPropagation()
        })

        modal.addEventListener('close', () => {
            if (!croppedBlobs.has(widgetId)) {
                fileInput.value = ''
            }
            if (currentCropper) {
                currentCropper.destroy()
                currentCropper = null
            }
        })
    })
}

const initCropper = (imageElement, modal) => {
    if (currentCropper) {
        currentCropper.destroy()
        currentCropper = null
    }

    currentCropper = new Cropper(imageElement, {
        aspectRatio: 1,
        viewMode: 1,
        dragMode: 'move',
        modal: false,
        highlight: false,
        autoCropArea: 1,
        restore: false,
        guides: true,
        center: false,
        cropBoxMovable: true,
        cropBoxResizable: true,
        toggleDragModeOnDblclick: false,
        ready: () => {
            // Add circle overlay to show circular preview area
            const cropBox = modal.querySelector('.cropper-crop-box')
            if (cropBox && !cropBox.querySelector('.circle-overlay')) {
                const circleOverlay = document.createElement('div')
                circleOverlay.className = 'circle-overlay'
                cropBox.appendChild(circleOverlay)
            }
        }
    })
}

const handleFormSubmit = () => {
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', (e) => {
            const widgets = form.querySelectorAll('.avatar-crop-widget')
            let needsProcessing = false

            widgets.forEach(widget => {
                const widgetId = widget.dataset.widgetId
                const blob = croppedBlobs.get(widgetId)

                if (blob) {
                    // Prevent form submission until we process the image
                    needsProcessing = true
                    e.preventDefault()

                    const fileInput = widget.querySelector('.avatar-file-input')
                    const file = new File([blob], 'avatar.webp', { type: 'image/webp' })
                    const dataTransfer = new DataTransfer()
                    dataTransfer.items.add(file)
                    fileInput.files = dataTransfer.files
                    croppedBlobs.delete(widgetId)
                }
            })

            if (needsProcessing) {
                setTimeout(() => form.submit(), 0)
            }
        }, { capture: true })
    })
}

onReady(() => {
    initAvatarCrop()
    handleFormSubmit()
})
