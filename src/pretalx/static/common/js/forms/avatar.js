// SPDX-FileCopyrightText: 2017-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

function setImage(url) {
    const image = document.querySelector('.avatar-form img');
    const imageWrapper = document.querySelector('.avatar-form .form-image-preview');
    const imageLink = imageWrapper.querySelector('a');
    image.src = url;
    imageLink.href = url;
    imageLink.dataset.lightbox = url;
    imageWrapper.classList.remove('d-none');
}

const updateFileInput = (ev) => {
    // Skip if this is the avatar crop widget - it handles its own preview
    if (ev.target.closest('.avatar-crop-widget')) return

    const imageSelected = ev.target.value !== '';

    if (imageSelected) {
        ev.target.closest('.avatar-form').querySelector('input[type=checkbox]').checked = false;
        const files = ev.target.files;
        if (files) {
            const reader = new FileReader();
            reader.onload = (e) => setImage(e.target.result);
            reader.readAsDataURL(files[0]);
            ev.target.closest('.avatar-form').querySelector('input[type=checkbox]').checked = false;
        } else if (ev.target.closest('.avatar-form').querySelector('img').dataset.avatar) {
            setImage(ev.target.closest('.avatar-form').querySelector('img').dataset.avatar);
            ev.target.closest('.avatar-form').querySelector('input[type=checkbox]').checked = false;
        } else {
            ev.target.closest('.avatar-form').querySelector('.form-image-preview').classList.add('d-none');
        }
    } else if (ev.target.closest('.avatar-form').querySelector('img').dataset.avatar) {
        setImage(ev.target.closest('.avatar-form').querySelector('img').dataset.avatar);
        ev.target.closest('.avatar-form').querySelector('input[type=checkbox]').checked = false;
    } else {
        ev.target.closest('.avatar-form').querySelector('.form-image-preview').classList.add('d-none');
    }
}

const updateCheckbox = (ev) => {
    if (ev.target.checked) {
        ev.target.closest('.avatar-form').querySelector('input[type=file]').value = '';
        ev.target.closest('.avatar-form').querySelector('.form-image-preview').classList.add('d-none');
    } else if (ev.target.closest('.avatar-form').querySelector('img').dataset.avatar) {
        setImage(ev.target.closest('.avatar-form').querySelector('img').dataset.avatar);
    } else {
        ev.target.closest('.avatar-form').querySelector('.form-image-preview').classList.add('d-none');
    }
}

const initFileInput = function () {
    document.querySelectorAll(".avatar-form").forEach(form => {
        const hasCropWidget = form.querySelector('.avatar-crop-widget');

        if (!hasCropWidget) {
            // Legacy behavior for non-cropping widgets
            const preview = form.querySelector(".form-image-preview");
            if (preview) {
                preview.remove();
            }
        }

        document.querySelectorAll('.avatar-upload input[type=file]').forEach((element) => {
            element.addEventListener('change', updateFileInput)
        })
        document.querySelectorAll('.avatar-upload input[type=checkbox]').forEach((element) => {
            element.addEventListener('change', updateCheckbox)
        })
    })
}

onReady(initFileInput)
