/**
 * Romanian translations for static UI strings. Used everywhere via t("key").
 * Dynamic content (categories, video titles, descriptions, tags) is shown as-is.
 */
const RO = {
  // Brand / tagline
  "site.tagline": "Vezi hentai subtitrat în limba română la calitate 1080P - 4096P.",
  "site.welcome": "Bun venit pe",

  // Sidebar nav
  "nav.browse": "Navigare",
  "nav.home": "Acasă",
  "nav.popular": "Populare",
  "nav.discover": "Descoperă",
  "nav.allEpisodes": "Toate Episoadele",
  "nav.shorts": "Shorts",
  "nav.contact": "Contact",
  "nav.upload": "Încarcă",
  "nav.adminPanel": "Panou Admin",
  "nav.categories": "Categorii",

  // Right sidebar
  "right.signIn": "Autentificare",
  "right.signOut": "Ieșire",
  "right.createAccount": "Creează cont",
  "right.profile": "Profil",
  "right.proTitle": "Devino PRO",
  "right.proSubtitle": "Deblochează videoclipuri premium, conținut exclusiv și multe altele.",
  "right.upgradeNow": "Activează acum",
  "right.recommended": "Recomandate",
  "right.packages": "Pachete",
  "right.views": "vizualizări",
  "right.pro": "PRO",

  // Home
  "home.latest": "Ultimele Încărcări",
  "home.popular": "Cele mai Vizionate",
  "home.discover": "Descoperă",
  "home.lastShorts": "Ultimele Shorts adăugate",
  "home.seeMore": "Vezi mai multe",
  "home.empty.title": "Niciun videoclip încă",
  "home.empty.body": "Fii primul care încarcă!",

  // Pages
  "page.popular": "Cele mai Vizionate",
  "page.discover": "Descoperă",
  "page.allEpisodes": "Toate Episoadele",
  "page.shorts": "Shorts",
  "page.loadMore": "Încarcă mai multe",
  "page.loading": "Se încarcă...",

  // Auth
  "auth.signIn": "Autentificare",
  "auth.signIn.subtitle": "Continuă pe",
  "auth.signIn.btn": "Autentifică-te",
  "auth.signIn.busy": "Se autentifică...",
  "auth.noAccount": "Nu ai cont?",
  "auth.createOne": "Creează unul",
  "auth.register": "Creează cont",
  "auth.register.subtitle": "Înscriere gratuită",
  "auth.register.btn": "Înregistrează-te",
  "auth.register.busy": "Se creează...",
  "auth.hasAccount": "Ai deja cont?",
  "auth.signInInstead": "Autentifică-te",
  "auth.email": "Email",
  "auth.username": "Nume utilizator",
  "auth.password": "Parolă",
  "auth.welcomeBack": "Bine ai revenit!",
  "auth.registered": "Cont creat!",
  "auth.checkEmail": "Verifică emailul pentru a-ți activa contul.",

  // Upload
  "upload.title": "Încarcă videoclip",
  "upload.file": "Fișier video",
  "upload.titleField": "Titlu",
  "upload.description": "Descriere",
  "upload.tags": "Etichete (separate prin virgulă)",
  "upload.category": "Categorie",
  "upload.access": "Acces",
  "upload.access.free": "Toți (gratuit)",
  "upload.access.pro": "Doar utilizatori PRO",
  "upload.isShort": "Acesta este un Shorts?",
  "upload.isShort.help": "Activează pentru clipuri scurte verticale.",
  "upload.btn": "Încarcă",
  "upload.busy": "Se încarcă",
  "upload.processing.title": "Se procesează videoclipul tău",
  "upload.processing.body": "Poți închide această pagină în orice moment — vom continua conversia în fundal. Vei putea vedea videoclipul de îndată ce cel puțin o rezoluție este gata.",
  "upload.pickThumb": "Alege o miniatură (10 generate):",
  "upload.viewVideo": "Vezi videoclipul",
  "upload.complete": "Încărcare completă. Se procesează...",
  "upload.failed": "Procesarea a eșuat:",

  // Player
  "player.processing": "Videoclipul este în curs de procesare, te rugăm să aștepți.",
  "player.proLocked": "Conținut PRO",
  "player.proLocked.body": "Upgrade la PRO pentru a vedea acest videoclip",
  "player.upgrade": "Activează acum",

  // Video meta
  "video.views": "vizualizări",
  "video.uploader": "Încărcat de",

  // Comments
  "comments.title": "Comentarii",
  "comments.placeholder": "Adaugă un comentariu",
  "comments.signInToComment": "Autentifică-te pentru a comenta.",
  "comments.empty": "Nu există comentarii încă.",

  // Profile
  "profile.videos": "Videoclipuri",
  "profile.changeAvatar": "Avatar",
  "profile.changeCover": "Copertă",
  "profile.confirmDelete": "Șterge acest videoclip?",
  "profile.deleted": "Videoclip șters",

  // Pro
  "pro.title": "Devino",
  "pro.subtitle": "Deblochează conținut premium, videoclipuri exclusive și o experiență fără reclame.",
  "pro.active": "Ești deja membru PRO. Expiră:",
  "pro.feature.watchAll": "Vezi toate videoclipurile PRO",
  "pro.feature.adFree": "Experiență fără reclame",
  "pro.feature.support": "Suport prioritar",
  "pro.subscribe": "Abonează-te",
  "pro.subscribing": "Se redirecționează...",
  "pro.empty": "Nu există pachete active.",

  // Contact
  "contact.title": "Contactează-ne",
  "contact.subtitle": "Ai o întrebare sau feedback? Trimite-ne un mesaj.",
  "contact.titleField": "Titlu",
  "contact.message": "Mesaj",
  "contact.email": "Email utilizator",
  "contact.send": "Trimite",
  "contact.sending": "Se trimite...",
  "contact.sent": "Mesaj trimis. Vom reveni cu un răspuns în curând.",

  // Common
  "common.cancel": "Anulează",
  "common.save": "Salvează",
  "common.delete": "Șterge",
  "common.edit": "Editează",
  "common.back": "Înapoi",
  "common.close": "Închide",
};

export function t(key, fallback) {
  return RO[key] ?? fallback ?? key;
}

export default RO;
