// Login: keep the Astro ID upper-case as it is typed and clear the error state on edit.

const input = document.querySelector('.field__input--id');
const form = document.querySelector('.login-form');

if (input && form) {
  input.addEventListener('input', () => {
    const { selectionStart, selectionEnd } = input;
    input.value = input.value.toUpperCase();
    input.setSelectionRange(selectionStart, selectionEnd);
    form.classList.remove('is-wrong');
    input.removeAttribute('aria-invalid');
  });
}

const canvas = document.querySelector('[data-scene-canvas]');
if (canvas) {
  import('../astro3d.js')
    .then(({ mountHero }) => mountHero(canvas, { variant: 'login' }))
    .then((scene) => { if (scene) document.querySelector('[data-scene]')?.classList.add('has-webgl'); })
    .catch(() => { /* the CSS horizon stays as the fallback */ });
}
