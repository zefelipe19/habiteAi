document.addEventListener('alpine:init', () => {
    Alpine.data('homeCarousel', () => ({
        active: 0,
        count: 0,
        playing: false,
        hovering: false,
        timer: null,

        init() {
            this.count = this.$root.querySelectorAll('[data-featured-slide]').length;
            this.$root.dataset.carouselReady = '';
            this.playing = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            this.timer = window.setInterval(() => {
                if (this.playing && !this.hovering && !document.hidden) {
                    this.advance(1);
                }
            }, 5500);
        },

        advance(direction) {
            this.active = (this.active + direction + this.count) % this.count;
        },

        move(direction) {
            this.playing = false;
            this.advance(direction);
        },

        destroy() {
            window.clearInterval(this.timer);
        },
    }));
});
