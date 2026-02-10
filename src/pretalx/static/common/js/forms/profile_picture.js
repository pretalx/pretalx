// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

let currentCropper = null
const croppedBlobs = new Map()

const initProfilePicture = () => {
    document.querySelectorAll('.pp-widget').forEach(widget => {
        const widgetId = widget.dataset.widgetId
        const actionInput = widget.querySelector('.pp-action-input')
        const fileInput = widget.querySelector('.pp-file-input')
        const editBtn = widget.querySelector('.pp-edit-btn')
        const dialog = widget.querySelector('.pp-dialog')
        const selectionView = widget.querySelector('.pp-selection-view')
        const cropView = widget.querySelector('.pp-crop-view')
        const uploadZone = widget.querySelector('.pp-upload-zone')
        const cropImage = widget.querySelector('.pp-crop-image')
        const cropApply = widget.querySelector('.pp-crop-apply')
        const cropBack = widget.querySelector('.pp-crop-back')
        const removeBtn = widget.querySelector('.pp-remove-btn')
        const preview = widget.querySelector('.pp-preview')
        const previewImg = widget.querySelector('.pp-preview-img')

        if (!dialog || !editBtn) return

        const openDialog = () => {
            showSelection()
            dialog.showModal()
        }

        const showSelection = () => {
            selectionView.hidden = false
            cropView.hidden = true
            if (currentCropper) {
                currentCropper.destroy()
                currentCropper = null
            }
        }

        const showCrop = (src) => {
            selectionView.hidden = true
            cropView.hidden = false
            cropImage.src = src
            initCropper(cropImage)
        }

        const updatePreview = (url) => {
            if (url) {
                if (previewImg) {
                    previewImg.src = url
                } else {
                    const img = document.createElement('img')
                    img.src = url
                    img.alt = ''
                    img.className = 'pp-preview-img'
                    preview.innerHTML = ''
                    preview.appendChild(img)
                }
                preview.classList.remove('pp-empty')
            } else {
                preview.innerHTML = '<i class="fa fa-user pp-placeholder-icon"></i>'
                preview.classList.add('pp-empty')
            }
        }

        // Open dialog
        editBtn.addEventListener('click', openDialog)
        preview.addEventListener('click', openDialog)
        preview.style.cursor = 'pointer'

        // Upload zone click
        uploadZone.addEventListener('click', () => fileInput.click())
        uploadZone.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                fileInput.click()
            }
        })

        // Drag and drop
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault()
            uploadZone.classList.add('pp-dragover')
        })
        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('pp-dragover')
        })
        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault()
            uploadZone.classList.remove('pp-dragover')
            const file = e.dataTransfer.files[0]
            if (file && file.type.startsWith('image/')) {
                loadFileForCrop(file)
            }
        })

        // File input change
        fileInput.addEventListener('change', () => {
            const file = fileInput.files[0]
            if (file) loadFileForCrop(file)
        })

        const loadFileForCrop = (file) => {
            if (!file.type.startsWith('image/')) return
            const reader = new FileReader()
            reader.onload = (e) => showCrop(e.target.result)
            reader.readAsDataURL(file)
        }

        // Crop: apply
        cropApply.addEventListener('click', () => {
            if (!currentCropper) return

            const btnText = cropApply.textContent
            cropApply.innerHTML = `<i class="fa fa-cog animate-spin pr-0"></i> ${btnText}`
            cropApply.classList.add('disabled')

            const canvas = currentCropper.getCroppedCanvas({
                width: 1024,
                height: 1024,
                imageSmoothingEnabled: true,
                imageSmoothingQuality: 'high',
            })

            canvas.toBlob((blob) => {
                croppedBlobs.set(widgetId, blob)
                const previewUrl = canvas.toDataURL('image/webp', 0.95)
                updatePreview(previewUrl)
                actionInput.value = 'upload'

                cropApply.textContent = btnText
                cropApply.classList.remove('disabled')
                dialog.close()
            }, 'image/webp', 0.95)
        })

        // Crop: back
        cropBack.addEventListener('click', showSelection)

        // Select existing picture
        widget.querySelectorAll('.pp-picture-option').forEach(btn => {
            btn.addEventListener('click', () => {
                const pk = btn.dataset.pk
                const url = btn.dataset.url
                actionInput.value = `select_${pk}`
                updatePreview(url)
                dialog.close()
            })
        })

        // Remove picture
        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                actionInput.value = 'remove'
                updatePreview(null)
                dialog.close()
            })
        }

        // Dialog close: reset if no action was taken
        dialog.addEventListener('close', () => {
            if (currentCropper) {
                currentCropper.destroy()
                currentCropper = null
            }
            if (!croppedBlobs.has(widgetId) && actionInput.value === 'keep') {
                fileInput.value = ''
            }
        })
    })
}

const initCropper = (imageElement) => {
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
            const cropBox = imageElement.closest('.pp-crop-container').querySelector('.cropper-crop-box')
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
            const widgets = form.querySelectorAll('.pp-widget')
            let needsProcessing = false

            widgets.forEach(widget => {
                const widgetId = widget.dataset.widgetId
                const blob = croppedBlobs.get(widgetId)

                if (blob) {
                    needsProcessing = true
                    e.preventDefault()

                    const fileInput = widget.querySelector('.pp-file-input')
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
    initProfilePicture()
    handleFormSubmit()
})
