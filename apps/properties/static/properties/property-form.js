document.addEventListener('alpine:init', () => {
    const invalidControl = 'input:invalid, select:invalid, textarea:invalid';

    Alpine.data('propertyForm', () => ({
        step: 1,
        stepCount: 0,
        photos: [],

        init() {
            this.stepCount = this.$root.querySelectorAll('[data-property-step]').length;
            this.$root.noValidate = true;

            const serverError = this.$root.querySelector(
                '[data-property-step] :is([aria-invalid="true"], [data-step-error])',
            );
            if (serverError) {
                this.showStep(this.stepFor(serverError));
            }
        },

        get progressLabel() {
            return `Etapa ${this.step} de ${this.stepCount}`;
        },

        get submitLabel() {
            return this.step < this.stepCount ? 'Continuar' : 'Salvar rascunho';
        },

        addPhotos(input) {
            if (typeof DataTransfer !== 'function') {
                return;
            }
            for (const file of input.files) {
                this.photos.push({file, url: URL.createObjectURL(file), title: ''});
            }
            this.syncPhotoInput(input);
        },

        removePhoto(index) {
            const [photo] = this.photos.splice(index, 1);
            URL.revokeObjectURL(photo.url);

            const input = this.$refs.photoPicker.querySelector('input');
            this.syncPhotoInput(input);
            input.focus();
        },

        syncPhotoInput(input) {
            const selection = new DataTransfer();
            for (const photo of this.photos) {
                selection.items.add(photo.file);
            }
            input.files = selection.files;
        },

        destroy() {
            for (const photo of this.photos) {
                URL.revokeObjectURL(photo.url);
            }
        },

        stepFor(field) {
            return Number(field.closest('[data-property-step]').dataset.propertyStep);
        },

        panel(step) {
            return this.$root.querySelector(`[data-property-step="${step}"]`);
        },

        showStep(step, invalidField) {
            this.step = step;
            this.$nextTick(() => {
                if (invalidField) {
                    invalidField.reportValidity();
                    return;
                }
                this.panel(step).querySelector('legend').focus();
            });
        },

        back() {
            this.showStep(this.step - 1);
        },

        submit(event) {
            if (this.step < this.stepCount) {
                event.preventDefault();
                const invalidField = this.panel(this.step).querySelector(invalidControl);
                if (invalidField) {
                    invalidField.reportValidity();
                } else {
                    this.showStep(this.step + 1);
                }
                return;
            }

            const invalidField = this.$root.querySelector(invalidControl);
            if (invalidField) {
                event.preventDefault();
                this.showStep(this.stepFor(invalidField), invalidField);
            }
        },
    }));
});
