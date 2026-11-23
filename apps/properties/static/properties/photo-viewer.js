const photoViewer = document.querySelector('[data-photo-viewer]');

if (typeof photoViewer?.showModal === 'function') {
    const photo = photoViewer.querySelector('img');
    const closeButton = photoViewer.querySelector('[data-photo-close]');
    let openedFrom;

    document.addEventListener('click', (event) => {
        const thumbnail = event.target.closest?.('[data-photo-preview]');
        if (!thumbnail || event.defaultPrevented || photoViewer.open
            || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) {
            return;
        }

        const thumbnailImage = thumbnail.querySelector('img');
        const source = thumbnail.href || thumbnailImage.currentSrc || thumbnailImage.src;
        if (!source) {
            return;
        }

        event.preventDefault();
        openedFrom = thumbnail;
        photo.alt = thumbnail.dataset.photoDescription || thumbnailImage.alt;
        photo.src = source;
        photoViewer.showModal();
    });

    closeButton.addEventListener('click', () => photoViewer.close());
    photoViewer.addEventListener('click', (event) => {
        if (event.target === photoViewer) {
            photoViewer.close();
        }
    });
    photoViewer.addEventListener('close', () => {
        photo.removeAttribute('src');
        openedFrom?.focus({preventScroll: true});
        openedFrom = undefined;
    });
}
