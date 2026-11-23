<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
type User={username:string;role:string;csrf:string};
type Ticket={id:string;title:string;body:string;status:string;version:number;created_at:string};
type Attachment={id:string;mime:string;size:number};
type Job={id:string;status:string;attempts:number;created_at:string};
const user=ref<User|null>(null),busy=ref(false),notice=ref(''),error=ref('');
const username=ref(''),password=ref(''),tickets=ref<Ticket[]>([]),jobs=ref<Job[]>([]),selected=ref<Ticket|null>(null),attachments=ref<Attachment[]>([]);
const intent=ref<{model_version:string;suggestions:{category:string;margin:number}[];notice:string}|null>(null);
async function suggestIntent(){if(selected.value)await run(async()=>{intent.value=await(await api('/api/tickets/'+selected.value!.id+'/intent',{method:'POST'})).json();});}
const view=ref('tickets'),search=ref(''),title=ref(''),body=ref(''),file=ref<File|null>(null),createOpen=ref(false);
const filtered=computed(()=>tickets.value.filter(t=>(t.title+' '+t.body).toLowerCase().includes(search.value.toLowerCase())));
const pageNumber=ref(1);
const pageCount=computed(()=>Math.max(1,Math.ceil(filtered.value.length/10)));
const pageTickets=computed(()=>filtered.value.slice((pageNumber.value-1)*10,pageNumber.value*10));
watch(search,()=>{pageNumber.value=1;});
const labels:Record<string,string>={open:'Ouvert',in_progress:'En cours',closed:'Résolu',pending:'En attente',processing:'En traitement',complete:'Prêt',failed:'Échec'};
async function api(path:string,options:RequestInit={}){
 const headers=new Headers(options.headers);if(options.body && typeof options.body==='string')headers.set('Content-Type','application/json');
 if(user.value)headers.set('X-CSRF-Token',user.value.csrf);
 const r=await fetch(path,{...options,headers,credentials:'same-origin'});
 if(!r.ok){let detail='Service indisponible';try{const x=await r.json();detail=typeof x.detail==='string'?x.detail:'Vérifier les informations saisies';}catch{}if(r.status===401)user.value=null;throw new Error(detail);}
 return r;
}
async function run(action:()=>Promise<void>){busy.value=true;error.value='';notice.value='';try{await action();}catch(e){error.value=e instanceof Error?e.message:'Une erreur est survenue';}finally{busy.value=false;}}
async function refresh(){tickets.value=await(await api('/api/tickets')).json();pageNumber.value=1;}
async function login(){await run(async()=>{user.value=await(await api('/api/login',{method:'POST',body:JSON.stringify({username:username.value,password:password.value})})).json();password.value='';await refresh();notice.value='Connexion établie.';});}
async function logout(){await run(async()=>{await api('/api/logout',{method:'POST'});user.value=null;selected.value=null;tickets.value=[];jobs.value=[];notice.value='Vous êtes déconnecté.';});}
async function createTicket(){await run(async()=>{const t=await(await api('/api/tickets',{method:'POST',body:JSON.stringify({title:title.value,body:body.value})})).json();title.value='';body.value='';createOpen.value=false;await refresh();await open(t);notice.value='Ticket créé.';});}
async function open(t:Ticket){intent.value=null;selected.value=await(await api('/api/tickets/'+t.id)).json();attachments.value=await(await api('/api/tickets/'+t.id+'/attachments')).json();}
async function status(next:string){if(!selected.value)return;await run(async()=>{const t=await(await api('/api/tickets/'+selected.value!.id,{method:'PATCH',body:JSON.stringify({status:next,version:selected.value!.version,assign_to_self:true})})).json();await refresh();await open(t);notice.value='Statut mis à jour.';});}
function chosen(event:Event){file.value=(event.target as HTMLInputElement).files?.[0]??null;}
async function upload(){if(!file.value||!selected.value)return;await run(async()=>{await api('/api/tickets/'+selected.value!.id+'/attachments',{method:'POST',headers:{'Content-Type':file.value!.type},body:file.value});await open(selected.value!);file.value=null;notice.value='Pièce jointe enregistrée.';});}
async function download(path:string,name:string){await run(async()=>{const blob=await(await api(path)).blob();const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);notice.value='Téléchargement préparé.';});}
async function loadJobs(){jobs.value=await(await api('/api/exports')).json();}
async function showJobs(){view.value='exports';await run(loadJobs);}
async function requestExport(){await run(async()=>{await api('/api/exports',{method:'POST'});await loadJobs();notice.value='Demande enregistrée. Le worker prépare votre fichier.';});}
let timer:ReturnType<typeof setInterval>|undefined;
onMounted(async()=>{try{user.value=await(await api('/api/me')).json();await refresh();}catch{}timer=setInterval(()=>{if(user.value&&view.value==='exports')loadJobs().catch(()=>{});},2000);});
onUnmounted(()=>{if(timer)clearInterval(timer);});
function date(value:string){return new Intl.DateTimeFormat('fr-FR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value));}
</script>
<template>
 <a href="#main" class="skip">Aller au contenu</a>
 <div class="shell">
  <aside class="sidebar">
   <a class="brand" href="/" aria-label="Accueil de l’espace support"><span class="brand-mark" aria-hidden="true">s.</span><span>Espace support<small>RNCP40875 · BC3</small></span></a>
   <div class="workspace"><span class="dot" aria-hidden="true"></span> Démonstration locale</div>
   <nav aria-label="Navigation principale" v-if="user">
    <button :aria-current="view==='tickets'?'page':undefined" @click="view='tickets'">Tickets <span>{{tickets.length}}</span></button>
    <button :aria-current="view==='exports'?'page':undefined" @click="showJobs">Exports asynchrones</button>
   </nav>
   <div class="sidebar-bottom"><p>Des données privées.<br>Une chaîne vérifiable.</p><small>Thomas Gassmann<br>Projet individuel</small></div>
  </aside>
  <div class="workspace-content">
   <header class="topbar"><span>Plateforme / <strong>{{user?(view==='tickets'?'Tickets':'Exports'):'Connexion'}}</strong></span><div v-if="user" class="account"><span>{{user.username}} <small>{{user.role==='agent'?'Agent':'Demandeur'}}</small></span><button class="quiet" @click="logout" :disabled="busy">Se déconnecter</button></div></header>
   <main id="main" tabindex="-1">
    <div class="messages" aria-live="polite" role="status"><p class="success" v-if="notice">{{notice}}</p><p class="error" v-if="error">{{error}}</p></div>
    <section v-if="!user" class="login">
     <p class="eyebrow">ACCÈS À LA PLATEFORME</p><h1>Un espace pour<br>résoudre vos demandes.</h1><p>Connectez-vous pour créer un ticket, ajouter une pièce jointe et suivre son traitement.</p>
     <form @submit.prevent="login" class="login-form"><label for="username">Identifiant</label><input id="username" v-model="username" required autocomplete="username" minlength="3" maxlength="64"><label for="password">Mot de passe</label><input id="password" v-model="password" type="password" required autocomplete="current-password" maxlength="200"><button class="primary" :disabled="busy">{{busy?'Connexion…':'Se connecter'}}</button></form>
     <p class="muted">Accès local uniquement. Les comptes sont créés par l’administrateur du projet ; aucun identifiant n’est intégré au code.</p>
    </section>
    <template v-else-if="view==='tickets'">
     <div class="heading"><div><p class="eyebrow">SUIVI DES DEMANDES</p><h1>Vos tickets, au même endroit.</h1><p>Consultez les échanges et gardez les pièces utiles à portée de main.</p></div><button class="primary" @click="createOpen=!createOpen" :aria-expanded="createOpen">{{createOpen?'Fermer le formulaire':'Nouveau ticket'}}</button></div>
     <form v-if="createOpen" @submit.prevent="createTicket" class="panel ticket-form"><h2>Créer une demande</h2><label for="title">Objet</label><input id="title" v-model="title" required minlength="3" maxlength="160"><label for="body">Description</label><textarea id="body" v-model="body" required minlength="3" maxlength="10000" rows="4"></textarea><div><button class="primary" :disabled="busy">Créer le ticket</button></div></form>
     <div class="stats"><div><span>Tickets consultables</span><strong>{{tickets.length}}</strong><small>200 derniers au maximum</small></div><div><span>À traiter</span><strong>{{tickets.filter(t=>t.status==='open').length}}</strong><small>Dans cette liste</small></div><div><span>En cours</span><strong>{{tickets.filter(t=>t.status==='in_progress').length}}</strong><small>Dans cette liste</small></div></div>
     <div class="ticket-columns"><section class="panel"><div class="panel-title"><h2>Dernières demandes</h2><button class="quiet" @click="run(refresh)" :disabled="busy">Actualiser</button></div><label for="search" class="sr-only">Rechercher dans les tickets chargés</label><input id="search" type="search" v-model="search" placeholder="Rechercher un ticket…">
      <p v-if="!filtered.length" class="empty">Aucun ticket à afficher. Créez votre première demande ou modifiez la recherche.</p>
      <ul class="ticket-list"><li v-for="t in pageTickets" :key="t.id"><button @click="run(()=>open(t))" :class="{active:selected?.id===t.id}"><span class="ticket-subject">{{t.title}}</span><span class="ticket-meta"><span :class="['badge',t.status]">{{labels[t.status]}}</span><time :datetime="t.created_at">{{date(t.created_at)}}</time></span></button></li></ul><div class="pagination" role="group" aria-label="Pagination des tickets"><button class="secondary" @click="pageNumber--" :disabled="pageNumber<=1">Précédents</button><span aria-live="polite">Page {{pageNumber}} sur {{pageCount}}</span><button class="secondary" @click="pageNumber++" :disabled="pageNumber>=pageCount">Suivants</button></div>
     </section><section class="panel detail" aria-label="Détail du ticket"><template v-if="selected"><div class="panel-title"><span :class="['badge',selected.status]">{{labels[selected.status]}}</span><small>Version {{selected.version}}</small></div><h2>{{selected.title}}</h2><p class="description">{{selected.body}}</p><div class="status-actions" v-if="user.role==='agent'"><button class="secondary" @click="status('in_progress')" :disabled="busy">Prendre en charge</button><button class="secondary" @click="status('closed')" :disabled="busy">Résoudre</button></div><hr><h3>Suggestion d’intention</h3><p class="muted">Pour les demandes rédigées en anglais. Vérifiez la suggestion avant toute utilisation.</p><button class="secondary" @click="suggestIntent" :disabled="busy">Suggérer une catégorie</button><div v-if="intent" aria-live="polite"><p class="muted">{{intent.notice}} Version {{intent.model_version}}.</p><ol><li v-for="s in intent.suggestions" :key="s.category">{{s.category.replaceAll('_',' ')}} · marge {{s.margin.toFixed(2)}}</li></ol></div><hr><h3>Pièces jointes privées</h3><p class="muted">PDF ou PNG, 5 Mio maximum. Les fichiers sont téléchargés en pièce jointe.</p><ul class="attachments"><li v-for="a in attachments" :key="a.id"><button class="quiet" @click="download('/api/attachments/'+a.id,'piece-'+a.id+(a.mime==='image/png'?'.png':'.pdf'))">Télécharger {{a.mime==='image/png'?'le PNG':'le PDF'}} · {{a.size}} octets</button></li></ul><form @submit.prevent="upload"><label for="file">Ajouter une pièce jointe</label><input id="file" type="file" accept="image/png,application/pdf" @change="chosen"><button class="secondary" :disabled="busy||!file">Ajouter le fichier</button></form></template><div v-else class="empty"><span class="empty-symbol" aria-hidden="true">↗</span><h2>Le détail de votre demande</h2><p>Sélectionnez un ticket pour consulter son contenu et ses pièces jointes.</p></div></section></div>
    </template>
    <section v-else class="exports"><div class="heading"><div><p class="eyebrow">TRAITEMENT ASYNCHRONE</p><h1>Vos exports, sans attendre.</h1><p>Le worker prépare un CSV des tickets auxquels vous avez accès.</p></div><button class="primary" @click="requestExport" :disabled="busy">Préparer un export</button></div><div class="notice">Le fichier est disponible lorsque son état passe à « Prêt ». Les résultats restent privés et les erreurs sont affichées.</div><div class="panel table-scroll" tabindex="0" role="region" aria-label="Tableau des exports"><table><caption>Les 50 derniers exports demandés</caption><thead><tr><th scope="col">Créé le</th><th scope="col">État</th><th scope="col">Tentatives</th><th scope="col">Fichier</th></tr></thead><tbody><tr v-for="j in jobs" :key="j.id"><td>{{date(j.created_at)}}</td><td><span :class="['badge',j.status]">{{labels[j.status]}}</span></td><td>{{j.attempts}}</td><td><button class="secondary" v-if="j.status==='complete'" @click="download('/api/exports/'+j.id+'/download','tickets-'+j.id+'.csv')">Télécharger le CSV</button><span v-else>{{j.status==='failed'?'Traitement en échec':'En préparation'}}</span></td></tr></tbody></table><p class="empty" v-if="!jobs.length">Aucun export pour le moment.</p></div></section>
    <footer>BC3 · Application de démonstration · Aucune décision bancaire ni envoi d’email</footer>
   </main>
  </div>
 </div>
</template>
