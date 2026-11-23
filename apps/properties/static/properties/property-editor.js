async function photoDraftTransaction(mode, operation) {
    const database = await new Promise((resolve, reject) => {
        const request = indexedDB.open('habiteai-property-editor', 1);
        request.onupgradeneeded = () => request.result.createObjectStore('photos');
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
        request.onblocked = () => reject(new Error('Draft storage is unavailable.'));
    });
    try {
        return await new Promise((resolve, reject) => {
            const transaction = database.transaction('photos', mode);
            const request = operation(transaction.objectStore('photos'));
            transaction.oncomplete = () => resolve(request.result);
            transaction.onabort = () => reject(transaction.error);
            transaction.onerror = () => reject(transaction.error || request.error);
        });
    } finally {
        database.close();
    }
}

function initializePropertyEditor(root, dialog) {
    const key = root.dataset.draftKey;
    const form = root.querySelector('[data-editor-form]');
    const fieldset = root.querySelector('[data-editor-fieldset]');
    const details = Array.from(form.querySelectorAll('[data-editor-details] :is(input, textarea, select)'));
    const removalBoxes = Array.from(form.querySelectorAll('input[name="removed_images"]'));
    const picker = form.querySelector('input[type="file"]');
    const photos = [];
    const photoList = root.querySelector('[data-editor-new-photos]');
    const photoTemplate = root.querySelector('[data-editor-photo-template]');
    const notice = root.querySelector('[data-editor-notice]');
    const warnings = root.querySelectorAll('[data-editor-storage-warning]');
    const errors = root.querySelector('[data-editor-errors]');
    const openButtons = root.querySelectorAll('[data-editor-open]');
    const discardButton = root.querySelector('[data-editor-discard]');
    const submitButton = root.querySelector('[data-editor-submit]');

    let photoWrites = Promise.resolve();
    let hasPhotoStorage = false;
    let missingPhotos = false;
    let localWarning = '';
    let photoWarning = '';
    let dirty = false;
    let saving = false;
    let nextPhotoId = 0;

    const valueOf = field => field.type === 'checkbox' ? field.checked : field.value;
    const initial = Object.fromEntries(details.map(field => [field.name, valueOf(field)]));
    form.noValidate = true;

    function refreshNotice() {
        notice.hidden = dialog.open || (!dirty && !missingPhotos);
        const warning = [localWarning, photoWarning].filter(Boolean).join(' ');
        for (const element of warnings) {
            element.hidden = !warning;
            element.textContent = warning;
        }
    }

    function rememberDraft() {
        const fields = Object.fromEntries(
            details.filter(field => valueOf(field) !== initial[field.name])
                .map(field => [field.name, valueOf(field)]),
        );
        const removedImages = removalBoxes.filter(box => box.checked).map(box => box.value);
        const imageTitles = photos.map(({id, title}) => ({id, title}));
        dirty = Boolean(Object.keys(fields).length || removedImages.length || imageTitles.length);
        try {
            if (dirty || missingPhotos) {
                localStorage.setItem(key, JSON.stringify({fields, removedImages, photos: imageTitles, missingPhotos}));
            } else {
                localStorage.removeItem(key);
            }
            localWarning = '';
        } catch {
            localWarning = 'O navegador não conseguiu guardar o rascunho neste dispositivo.';
        }
        refreshNotice();
    }

    function storePhotos() {
        const files = photos.map(({id, file}) => ({id, file}));
        hasPhotoStorage = true;
        photoWrites = photoWrites
            .then(() => photoDraftTransaction('readwrite', store =>
                files.length ? store.put(files, key) : store.delete(key),
            ))
            .then(() => {
                photoWarning = '';
            }, () => {
                photoWarning = 'O navegador não conseguiu guardar as novas fotos. Envie antes de sair da página.';
            })
            .then(refreshNotice);
        return photoWrites;
    }

    function renderPhotos() {
        photoList.replaceChildren();
        photoList.hidden = photos.length === 0;
        for (const photo of photos) {
            const item = photoTemplate.content.cloneNode(true);
            const thumbnail = item.querySelector('[data-photo-preview]');
            const image = item.querySelector('img');
            const title = item.querySelector('[data-editor-photo-title]');
            const remove = item.querySelector('[data-editor-remove-photo]');
            image.src = photo.url;
            image.alt = photo.file.name;
            title.id = `editor-photo-${photo.id}`;
            title.value = photo.title;
            item.querySelector('[data-editor-photo-label]').htmlFor = title.id;
            remove.setAttribute('aria-label', `Remover ${photo.file.name}`);

            function updateThumbnailLabel() {
                const description = photo.title || photo.file.name;
                thumbnail.dataset.photoDescription = description;
                thumbnail.setAttribute('aria-label', `Ampliar foto de ${description}`);
            }
            updateThumbnailLabel();
            title.addEventListener('input', () => {
                photo.title = title.value;
                updateThumbnailLabel();
            });
            remove.addEventListener('click', () => {
                photos.splice(photos.indexOf(photo), 1);
                URL.revokeObjectURL(photo.url);
                renderPhotos();
                rememberDraft();
                storePhotos();
                picker.focus();
            });
            photoList.append(item);
        }
    }

    async function restoreDraft() {
        let draft;
        try {
            draft = JSON.parse(localStorage.getItem(key));
        } catch {
            localWarning = 'O navegador não conseguiu recuperar o rascunho.';
        }
        if (!draft) {
            refreshNotice();
            return;
        }

        for (const field of details) {
            const value = draft.fields?.[field.name];
            if (typeof value === 'boolean' && field.type === 'checkbox') {
                field.checked = value;
            } else if (typeof value === 'string' && field.type !== 'checkbox') {
                field.value = value;
            }
        }
        for (const box of removalBoxes) {
            box.checked = Array.isArray(draft.removedImages) && draft.removedImages.includes(box.value);
        }
        const savedPhotos = Array.isArray(draft.photos) ? draft.photos : [];
        if (savedPhotos.length) {
            hasPhotoStorage = true;
            try {
                const files = await photoDraftTransaction('readonly', store => store.get(key));
                const filesById = new Map((files || []).map(({id, file}) => [id, file]));
                for (const {id, title} of savedPhotos) {
                    const file = filesById.get(id);
                    if (file) {
                        photos.push({id, file, title, url: URL.createObjectURL(file)});
                    }
                }
            } catch {
                // Other draft fields can still be restored without the files.
            }
        }
        missingPhotos = Boolean(draft.missingPhotos) || photos.length !== savedPhotos.length;
        if (missingPhotos) {
            photoWarning = 'Selecione novamente as fotos que não puderam ser recuperadas.';
        }
        renderPhotos();
        rememberDraft();
    }

    function showErrors(messages) {
        errors.replaceChildren();
        errors.hidden = messages.length === 0;
        for (const message of messages) {
            const paragraph = document.createElement('p');
            paragraph.className = 'mb-1';
            paragraph.textContent = message;
            errors.append(paragraph);
        }
        if (!errors.hidden) {
            errors.focus();
        }
    }

    function discardDraft() {
        form.reset();
        for (const photo of photos) {
            URL.revokeObjectURL(photo.url);
        }
        photos.length = 0;
        missingPhotos = false;
        photoWarning = '';
        renderPhotos();
        showErrors([]);
        rememberDraft();
        return hasPhotoStorage ? storePhotos() : photoWrites;
    }

    function setSaving(value) {
        saving = value;
        fieldset.disabled = value;
        submitButton.disabled = value;
        discardButton.disabled = value;
        for (const button of openButtons) {
            button.disabled = value;
        }
        submitButton.textContent = value ? 'Salvando…' : 'Salvar alterações';
        form.setAttribute('aria-busy', String(value));
    }

    picker.addEventListener('change', () => {
        if (!picker.files.length) {
            return;
        }
        for (const file of picker.files) {
            const id = crypto.randomUUID?.() ?? `${Date.now()}-${nextPhotoId++}`;
            photos.push({id, file, title: '', url: URL.createObjectURL(file)});
        }
        picker.value = '';
        missingPhotos = false;
        renderPhotos();
        rememberDraft();
        storePhotos();
    });
    form.addEventListener('input', rememberDraft);
    form.addEventListener('change', rememberDraft);

    for (const button of openButtons) {
        button.addEventListener('click', () => {
            dialog.showModal();
            refreshNotice();
        });
    }
    discardButton.addEventListener('click', () => {
        discardDraft();
        openButtons[0].focus();
    });
    const closeEditor = async () => {
        rememberDraft();
        await photoWrites;
        dialog.close();
    };
    root.querySelector('[data-editor-close]').addEventListener('click', closeEditor);
    dialog.addEventListener('cancel', event => {
        event.preventDefault();
        closeEditor();
    });
    dialog.addEventListener('close', refreshNotice);

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (saving) {
            return;
        }
        showErrors([]);
        const invalid = form.querySelector('input:invalid, select:invalid, textarea:invalid');
        if (invalid) {
            const section = invalid.closest('details');
            if (section) {
                section.open = true;
            }
            invalid.reportValidity();
            return;
        }

        const payload = new FormData(form);
        payload.delete(picker.name);
        payload.set('edited_fields', details.filter(field => valueOf(field) !== initial[field.name])
            .map(field => field.name).join(','));
        for (const photo of photos) {
            payload.append(picker.name, photo.file);
            payload.append('image_titles', photo.title);
        }
        setSaving(true);
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: payload,
                headers: {Accept: 'application/json'},
            });
            if (response.redirected || response.status === 403) {
                showErrors(['Entre novamente para salvar. Suas alterações ficam neste navegador.']);
                return;
            }
            const result = await response.json();
            if (!response.ok || !result.redirect) {
                showErrors(result.errors || ['Não foi possível salvar as alterações.']);
                return;
            }
            await discardDraft();
            window.location.assign(result.redirect);
        } catch {
            showErrors(['Não foi possível salvar as alterações. Tente novamente.']);
        } finally {
            setSaving(false);
        }
    });

    restoreDraft().finally(() => {
        for (const button of openButtons) {
            button.disabled = false;
        }
    });
}

const editor = document.querySelector('[data-property-editor]');
const dialog = editor?.querySelector('[data-editor-dialog]');
if (typeof dialog?.showModal === 'function') {
    initializePropertyEditor(editor, dialog);
}
