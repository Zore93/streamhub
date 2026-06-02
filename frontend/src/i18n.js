/**
 * Lightweight i18n. Two locales supported: English ("en") and Romanian ("ro").
 *
 *   - `useT()` hook reads the active locale from LanguageContext.
 *   - `t(lang, key)` standalone helper for callers without React context.
 *   - Falls back to English then to the key itself if a string is missing.
 */
const EN = {
  "site.tagline": "Watch hentai subtitled in Romanian in 1080P - 4096P quality.",
  "site.welcome": "Welcome to",
  "site.openMenu": "Open menu",
  "site.closeMenu": "Close menu",
  "site.language": "Language",

  // Sidebar nav
  "nav.browse": "Browse",
  "nav.home": "Home",
  "nav.popular": "Popular",
  "nav.discover": "Discover",
  "nav.allEpisodes": "All Episodes",
  "nav.shorts": "Shorts",
  "nav.contact": "Contact",
  "nav.upload": "Upload",
  "nav.adminPanel": "Admin Panel",
  "nav.categories": "Categories",
  "nav.noCategories": "No categories",

  // Right sidebar
  "right.signIn": "Sign In",
  "right.signOut": "Sign Out",
  "right.createAccount": "Create Account",
  "right.profile": "Profile",
  "right.proTitle": "Go PRO",
  "right.proSubtitle": "Unlock premium videos, exclusive content & more.",
  "right.upgradeNow": "Upgrade Now",
  "right.recommended": "Recommended",
  "right.packages": "Packages",
  "right.views": "views",
  "right.pro": "PRO",

  // Home
  "home.latest": "Latest Uploads",
  "home.popular": "Most Viewed",
  "home.discover": "Discover",
  "home.lastShorts": "Last Shorts added",
  "home.seeMore": "See more",
  "home.empty.title": "No videos yet",
  "home.empty.body": "Be the first to upload one!",

  // Pages
  "page.popular": "Most Viewed",
  "page.discover": "Discover",
  "page.allEpisodes": "All Episodes",
  "page.shorts": "Shorts",
  "page.loadMore": "Load more",
  "page.loading": "Loading...",
  "page.empty": "Nothing here yet.",

  // Discover filters
  "discover.searchPlaceholder": "Search videos by title…",
  "discover.filters": "Filters",
  "discover.clearAll": "Clear all",
  "discover.tier": "Access",
  "discover.tierAll": "All",
  "discover.tierFree": "Free videos",
  "discover.tierPro": "PRO videos",
  "discover.categories": "Categories (pick up to 2)",
  "discover.noResults": "No videos match your filters.",

  // Auth
  "auth.signIn": "Sign in",
  "auth.signIn.subtitle": "Continue to",
  "auth.signIn.btn": "Sign In",
  "auth.signIn.busy": "Signing in...",
  "auth.noAccount": "No account?",
  "auth.createOne": "Create one",
  "auth.register": "Create account",
  "auth.register.subtitle": "Join free",
  "auth.register.btn": "Sign Up",
  "auth.register.busy": "Creating...",
  "auth.hasAccount": "Have an account?",
  "auth.signInInstead": "Sign in",
  "auth.email": "Email",
  "auth.username": "Username",
  "auth.password": "Password",
  "auth.welcomeBack": "Welcome back!",
  "auth.registered": "Account created!",
  "auth.checkEmail": "Check your email to verify your account.",

  // Upload
  "upload.title": "Upload Video",
  "upload.file": "Video file",
  "upload.titleField": "Title",
  "upload.description": "Description",
  "upload.tags": "Tags (comma-separated)",
  "upload.category": "Category",
  "upload.categoryNone": "None",
  "upload.access": "Access",
  "upload.access.free": "Everyone (free)",
  "upload.access.pro": "PRO users only",
  "upload.isShort": "This is a Short?",
  "upload.isShort.help": "Toggle on for vertical short-form clips (≤ {dur}s, 9:16).",
  "upload.btn": "Upload",
  "upload.busy": "Uploading",
  "upload.processing.title": "Upload received — processing in background",
  "upload.processing.body": "You can close this page or navigate away. We'll keep transcoding in the background and the video becomes playable as soon as the first resolution finishes.",
  "upload.pickThumb": "Choose a thumbnail (10 generated):",
  "upload.viewVideo": "View video",
  "upload.complete": "Upload complete — processing in background.",
  "upload.failed": "Processing failed:",
  "upload.continueBrowsing": "Continue browsing",

  // Player
  "player.processing": "This video is being processed. Please wait — playback starts as soon as the first resolution is ready.",
  "player.proLocked": "PRO content",
  "player.proLocked.body": "Upgrade to PRO to watch this video",
  "player.upgrade": "Upgrade Now",

  // Video meta
  "video.views": "views",
  "video.uploader": "Uploaded by",

  // Comments
  "comments.title": "Comments",
  "comments.placeholder": "Add a comment",
  "comments.signInToComment": "Sign in to comment.",
  "comments.empty": "No comments yet.",

  // Profile
  "profile.videos": "Videos",
  "profile.changeAvatar": "Avatar",
  "profile.changeCover": "Cover",
  "profile.confirmDelete": "Delete this video?",
  "profile.deleted": "Video deleted",

  // Pro
  "pro.title": "Go",
  "pro.subtitle": "Unlock premium content, exclusive videos, and an ad-free experience.",
  "pro.active": "You are already a PRO member. Expires:",
  "pro.feature.watchAll": "Watch all PRO videos",
  "pro.feature.adFree": "Ad-free experience",
  "pro.feature.support": "Priority support",
  "pro.subscribe": "Subscribe",
  "pro.subscribing": "Redirecting...",
  "pro.empty": "No active packages.",

  // Contact
  "contact.title": "Contact us",
  "contact.subtitle": "Got a question or feedback? Drop us a message.",
  "contact.titleField": "Title",
  "contact.message": "Message",
  "contact.email": "Your email",
  "contact.send": "Send",
  "contact.sending": "Sending...",
  "contact.sent": "Message sent. We'll get back to you soon.",

  // Live chat
  "chat.title": "Live Chat",
  "chat.placeholder": "Type a message…",
  "chat.send": "Send",
  "chat.guestName": "Your nickname",
  "chat.guestNamePlaceholder": "Nickname (visible in chat)",
  "chat.startChatting": "Start chatting",
  "chat.connecting": "Connecting…",
  "chat.empty": "No messages yet. Say hi!",
  "chat.banned": "You are banned from chat.",
  "chat.banUser": "Ban from chat",
  "chat.deleteMessage": "Delete message",

  // Common
  "common.cancel": "Cancel",
  "common.save": "Save",
  "common.delete": "Delete",
  "common.edit": "Edit",
  "common.back": "Back",
  "common.close": "Close",
};

const RO = {
  "site.tagline": "Vezi hentai subtitrat în limba română la calitate 1080P - 4096P.",
  "site.welcome": "Bun venit pe",
  "site.openMenu": "Deschide meniul",
  "site.closeMenu": "Închide meniul",
  "site.language": "Limbă",

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
  "nav.noCategories": "Nicio categorie",

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

  "home.latest": "Ultimele Încărcări",
  "home.popular": "Cele mai Vizionate",
  "home.discover": "Descoperă",
  "home.lastShorts": "Ultimele Shorts adăugate",
  "home.seeMore": "Vezi mai multe",
  "home.empty.title": "Niciun videoclip încă",
  "home.empty.body": "Fii primul care încarcă!",

  "page.popular": "Cele mai Vizionate",
  "page.discover": "Descoperă",
  "page.allEpisodes": "Toate Episoadele",
  "page.shorts": "Shorts",
  "page.loadMore": "Încarcă mai multe",
  "page.loading": "Se încarcă...",
  "page.empty": "Nimic aici încă.",

  // Discover filters
  "discover.searchPlaceholder": "Caută videoclipuri după titlu…",
  "discover.filters": "Filtre",
  "discover.clearAll": "Șterge tot",
  "discover.tier": "Acces",
  "discover.tierAll": "Toate",
  "discover.tierFree": "Videoclipuri gratuite",
  "discover.tierPro": "Videoclipuri PRO",
  "discover.categories": "Categorii (alege maxim 2)",
  "discover.noResults": "Niciun videoclip nu corespunde filtrelor tale.",

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

  "upload.title": "Încarcă videoclip",
  "upload.file": "Fișier video",
  "upload.titleField": "Titlu",
  "upload.description": "Descriere",
  "upload.tags": "Etichete (separate prin virgulă)",
  "upload.category": "Categorie",
  "upload.categoryNone": "Niciuna",
  "upload.access": "Acces",
  "upload.access.free": "Toți (gratuit)",
  "upload.access.pro": "Doar utilizatori PRO",
  "upload.isShort": "Acesta este un Shorts?",
  "upload.isShort.help": "Activează pentru clipuri scurte verticale (≤ {dur}s, 9:16).",
  "upload.btn": "Încarcă",
  "upload.busy": "Se încarcă",
  "upload.processing.title": "Încărcare primită — procesare în fundal",
  "upload.processing.body": "Poți închide această pagină în orice moment. Vom continua conversia în fundal, iar videoclipul devine vizionabil de îndată ce prima rezoluție este gata.",
  "upload.pickThumb": "Alege o miniatură (10 generate):",
  "upload.viewVideo": "Vezi videoclipul",
  "upload.complete": "Încărcare completă — se procesează în fundal.",
  "upload.failed": "Procesarea a eșuat:",
  "upload.continueBrowsing": "Continuă navigarea",

  "player.processing": "Acest videoclip este în curs de procesare. Te rugăm să aștepți — redarea începe de îndată ce prima rezoluție este gata.",
  "player.proLocked": "Conținut PRO",
  "player.proLocked.body": "Upgrade la PRO pentru a vedea acest videoclip",
  "player.upgrade": "Activează acum",

  "video.views": "vizualizări",
  "video.uploader": "Încărcat de",

  "comments.title": "Comentarii",
  "comments.placeholder": "Adaugă un comentariu",
  "comments.signInToComment": "Autentifică-te pentru a comenta.",
  "comments.empty": "Nu există comentarii încă.",

  "profile.videos": "Videoclipuri",
  "profile.changeAvatar": "Avatar",
  "profile.changeCover": "Copertă",
  "profile.confirmDelete": "Șterge acest videoclip?",
  "profile.deleted": "Videoclip șters",

  "pro.title": "Devino",
  "pro.subtitle": "Deblochează conținut premium, videoclipuri exclusive și o experiență fără reclame.",
  "pro.active": "Ești deja membru PRO. Expiră:",
  "pro.feature.watchAll": "Vezi toate videoclipurile PRO",
  "pro.feature.adFree": "Experiență fără reclame",
  "pro.feature.support": "Suport prioritar",
  "pro.subscribe": "Abonează-te",
  "pro.subscribing": "Se redirecționează...",
  "pro.empty": "Nu există pachete active.",

  "contact.title": "Contactează-ne",
  "contact.subtitle": "Ai o întrebare sau feedback? Trimite-ne un mesaj.",
  "contact.titleField": "Titlu",
  "contact.message": "Mesaj",
  "contact.email": "Email utilizator",
  "contact.send": "Trimite",
  "contact.sending": "Se trimite...",
  "contact.sent": "Mesaj trimis. Vom reveni cu un răspuns în curând.",

  "chat.title": "Chat live",
  "chat.placeholder": "Scrie un mesaj…",
  "chat.send": "Trimite",
  "chat.guestName": "Pseudonimul tău",
  "chat.guestNamePlaceholder": "Pseudonim (vizibil în chat)",
  "chat.startChatting": "Începe să discuți",
  "chat.connecting": "Se conectează…",
  "chat.empty": "Niciun mesaj încă. Salută-i pe ceilalți!",
  "chat.banned": "Ești banat din chat.",
  "chat.banUser": "Banează din chat",
  "chat.deleteMessage": "Șterge mesaj",

  "common.cancel": "Anulează",
  "common.save": "Salvează",
  "common.delete": "Șterge",
  "common.edit": "Editează",
  "common.back": "Înapoi",
  "common.close": "Închide",
};

export const STRINGS = { en: EN, ro: RO };
export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "ro", label: "Română" },
];

export function t(lang, key, fallback) {
  const dict = STRINGS[lang] || EN;
  if (dict[key] != null) return dict[key];
  if (EN[key] != null) return EN[key];
  return fallback ?? key;
}

export default STRINGS;
