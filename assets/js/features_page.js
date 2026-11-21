/* =========================================
   Company: Seal and Lube, spol. s r.o.
   Author: Ing. Viliam Schneider
   File: assets/js/features_page.js
========================================= */

let menuTranslations = null;

document.addEventListener('DOMContentLoaded', () => {
    initLanguageSwitcher();
    initMobileMenu();

    const urlParams = new URLSearchParams(window.location.search);
    const lang = urlParams.get('lang') || localStorage.getItem('venvhub_lang') || 'sk';

    window.loadLanguage(lang, false);
});

async function loadMenuTranslations(lang) {
    try {
        if (!menuTranslations) {
            const res = await fetch('assets/preklady_menu.json');
            if (res.ok) menuTranslations = await res.json();
        }
        if (menuTranslations && menuTranslations[lang]) {
            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                if (menuTranslations[lang][key]) el.textContent = menuTranslations[lang][key];
            });
        }
    } catch (e) {
        console.error('Chyba menu prekladov:', e);
    }
}

window.loadLanguage = async function(lang, pushToHistory = true) {
    const container = document.getElementById('features-container');
    const label = document.getElementById('currentLangLabel');
    const filePath = `${lang}/features_text.html`;

    localStorage.setItem('venvhub_lang', lang);
    document.documentElement.lang = lang;

    const newUrl = `${window.location.pathname}?lang=${lang}`;
    if (pushToHistory) {
        window.history.pushState({ lang }, '', newUrl);
    } else {
        window.history.replaceState({ lang }, '', newUrl);
    }

    // Aktualizácia odkazov v hlavičke
    const homeLink = document.getElementById('navHomeLink');
    const homeLogo = document.getElementById('homeLogoLink');
    const manualLink = document.getElementById('navManualLink');
    if (homeLink) homeLink.href = `index.html?lang=${lang}`;
    if (homeLogo) homeLogo.href = `index.html?lang=${lang}`;
    if (manualLink) manualLink.href = `manual/index-manual.html?lang=${lang}`;

    try {
        await loadMenuTranslations(lang);

        const response = await fetch(filePath);
        if (!response.ok) throw new Error(`Súbor ${filePath} sa nenašiel.`);
        
        container.innerHTML = await response.text();

        if (label) {
            label.textContent = lang === 'sk' ? 'Slovenčina' : 'English';
        }
    } catch (err) {
        container.innerHTML = `<div style="color: red; padding: 20px;">Chyba načítania obsahu: ${err.message}</div>`;
    }

    document.getElementById('langDropdown')?.classList.remove('show');
};

function initLanguageSwitcher() {
    const langBtn = document.getElementById('langBtn');
    const langDropdown = document.getElementById('langDropdown');

    if (!langBtn || !langDropdown) return;

    langBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        langDropdown.classList.toggle('show');
    });

    langDropdown.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const targetLang = link.getAttribute('data-lang');
            if (targetLang) window.loadLanguage(targetLang);
        });
    });

    document.addEventListener('click', (e) => {
        if (!langBtn.contains(e.target) && !langDropdown.contains(e.target)) {
            langDropdown.classList.remove('show');
        }
    });
}

function initMobileMenu() {
    const menuToggle = document.getElementById('menuToggle');
    const navMenu = document.querySelector('.nav-menu');
    if (!menuToggle || !navMenu) return;

    menuToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        navMenu.classList.toggle('active');
        menuToggle.textContent = navMenu.classList.contains('active') ? '✕' : '☰';
    });
}