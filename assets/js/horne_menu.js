/* =========================================
   Company: Seal and Lube, spol. s r.o.
   Author: Ing. Viliam Schneider
   File: assets/js/horne_menu.js
========================================= */

let menuTranslations = null;

document.addEventListener('DOMContentLoaded', () => {
    initLanguageSwitcher();
    initMobileMenu();

    // 1. Zistiť jazyk: z URL -> ak nie je, tak z pamäte -> ak nie je, automaticky z x-default v HTML
    const urlParams = new URLSearchParams(window.location.search);
    let lang = urlParams.get('lang');

    if (!lang) {
        lang = localStorage.getItem('venvhub_lang') || getDefaultLanguage();
    }

    // 2. Načítať jazyk a zabezpečiť správny tvar URL (?lang=sk / ?lang=en)
    window.loadLanguage(lang, false);
});

/**
 * Zistí predvolený jazyk priamo z tagu <link rel="alternate" hreflang="x-default"> v hlavičke HTML
 */
function getDefaultLanguage() {
    const xDefaultLink = document.querySelector('link[hreflang="x-default"]');
    if (xDefaultLink && xDefaultLink.getAttribute('href')) {
        const match = xDefaultLink.getAttribute('href').match(/lang=([a-zA-Z-]+)/);
        if (match && match[1]) {
            return match[1];
        }
    }
    return 'sk'; // Záchranný fallback, ak by tag v HTML chýbal
}

/**
 * Načíta preklady horného menu
 */
async function loadMenuTranslations(lang) {
    try {
        if (!menuTranslations) {
            const response = await fetch('assets/preklady_menu.json');
            if (response.ok) {
                menuTranslations = await response.json();
            }
        }

        if (menuTranslations && menuTranslations[lang]) {
            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                if (menuTranslations[lang][key]) {
                    el.textContent = menuTranslations[lang][key];
                }
            });
        }
    } catch (error) {
        console.error('Chyba prekladov menu:', error);
    }
}

/**
 * Hlavná funkcia pre načítanie jazyka, zmenu URL a uloženie voľby
 */
window.loadLanguage = async function(lang, pushToHistory = true) {
    const container = document.getElementById('content-container');
    const label = document.getElementById('currentLangLabel');
    const filePath = `${lang}/index_text.html`;

    // 1. Uloženie do pamäte prehliadača
    localStorage.setItem('venvhub_lang', lang);

    // 2. Prepísanie URL adresy na tvar index.html?lang=sk / index.html?lang=en
    const newUrl = `${window.location.pathname}?lang=${lang}${window.location.hash}`;
    if (pushToHistory) {
        window.history.pushState({ lang: lang }, '', newUrl);
    } else {
        window.history.replaceState({ lang: lang }, '', newUrl);
    }

    try {
        // 3. Preklad položiek v hornom menu
        await loadMenuTranslations(lang);

        // 4. Aktualizácia SEO metadát, OpenGraph a Schema.org (z assets/js/seo/seo_title.js)
        if (typeof updateSEOMetadata === 'function') {
            updateSEOMetadata(lang);
        }

        // 5. Načítanie tela stránky (sk/index_text.html, en/index_text.html atď.)
        const response = await fetch(filePath);
        if (!response.ok) {
            throw new Error(`Súbor ${filePath} neexistuje.`);
        }

        const htmlContent = await response.text();
        if (container) {
            container.innerHTML = htmlContent;
        }

        // 6. Zmena textu na tlačidle výberu jazyka
        if (label) {
            label.textContent = lang === 'sk' ? 'Slovenčina' : (lang === 'en' ? 'English' : lang.toUpperCase());
        }

        initNavigationHighlight();

        // 7. Dotiahnutie verzie z GitHubu
        if (typeof fetchLatestGitHubRelease === 'function') {
            fetchLatestGitHubRelease();
        }

        // 8. Aktualizácia externých preklikov podľa aktuálneho jazyka
        const navFeatures = document.getElementById('navFeaturesLink');
        if (navFeatures) {
            navFeatures.href = `features.html?lang=${lang}`;
        }
        const navManual = document.querySelector('a[data-i18n="nav_manual"]');
        if (navManual) {
            navManual.href = `manual/index-manual.html?lang=${lang}`;
        }

        // >>> PRIDANÝ RIADOK PRE TLAČIDLO V BANNERI <<<
        const promoFeaturesBtn = document.getElementById('promoFeaturesBtn');
        if (promoFeaturesBtn) {
            promoFeaturesBtn.href = `features.html?lang=${lang}`;
        }

    } catch (error) {
        console.error('Chyba načítania obsahu:', error);
        if (container) {
            container.innerHTML = `<div style="color: red; padding: 20px;">Chyba pri načítavaní jazyka [${lang}]: ${error.message}</div>`;
        }
    }

    // Zatvorenie rozbalovacieho menu jazykov
    document.getElementById('langDropdown')?.classList.remove('show');
};

// Reakcia na tlačidlá Späť / Dopredu v prehliadači
window.addEventListener('popstate', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const lang = urlParams.get('lang') || getDefaultLanguage();
    window.loadLanguage(lang, false);
});

/**
 * Obsluha rozbaľovacieho menu jazykov
 */
function initLanguageSwitcher() {
    const langBtn = document.getElementById('langBtn');
    const langDropdown = document.getElementById('langDropdown');

    if (!langBtn || !langDropdown || langBtn.dataset.listener) return;
    langBtn.dataset.listener = 'true';

    // Otváranie / zatváranie dropdownu
    langBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        langDropdown.classList.toggle('show');
    });

    // Plynulé prepínanie jazyka pre používateľa (zabraňuje tvrdému reloadu)
    langDropdown.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const targetLang = link.getAttribute('data-lang');
            if (targetLang) {
                window.loadLanguage(targetLang);
            }
        });
    });

    // Zatvorenie dropdownu pri kliknutí mimo neho
    document.addEventListener('click', (e) => {
        if (!langBtn.contains(e.target) && !langDropdown.contains(e.target)) {
            langDropdown.classList.remove('show');
        }
    });
}

/**
 * Mobilné hamburger menu
 */
function initMobileMenu() {
    const menuToggle = document.getElementById('menuToggle');
    const navMenu = document.querySelector('.nav-menu');

    if (!menuToggle || !navMenu) return;

    menuToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        navMenu.classList.toggle('active');
        menuToggle.textContent = navMenu.classList.contains('active') ? '✕' : '☰';
    });

    navMenu.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            navMenu.classList.remove('active');
            menuToggle.textContent = '☰';
        });
    });

    document.addEventListener('click', (e) => {
        if (!navMenu.contains(e.target) && !menuToggle.contains(e.target)) {
            navMenu.classList.remove('active');
            menuToggle.textContent = '☰';
        }
    });
}

/**
 * Zvýraznenie aktívnej sekcie pri scrollovaní
 */
function initNavigationHighlight() {
    const navLinks = document.querySelectorAll('.nav-menu a');
    const sections = document.querySelectorAll('section');

    if (navLinks.length === 0 || sections.length === 0) return;

    window.addEventListener('scroll', () => {
        let current = '';
        sections.forEach(section => {
            const sectionTop = section.offsetTop - 100;
            if (window.scrollY >= sectionTop) {
                current = section.getAttribute('id');
            }
        });

        navLinks.forEach(link => {
            link.classList.remove('active');
            if (current && link.getAttribute('href') === `#${current}`) {
                link.classList.add('active');
            }
        });
    });
}