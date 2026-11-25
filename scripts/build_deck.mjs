// Support local éditable ; artefacts et chiffres issus exclusivement des preuves BC3.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {FileBlob,Presentation,PresentationFile} from '@oai/artifact-tool';
const root=path.resolve(process.env.BC3_ROOT||'../..');
const runtime=process.env.BC3_DOCUMENT_RUNTIME||'/Users/thomasgassmann/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const skill=process.env.BC3_PRESENTATION_SKILL||'/Users/thomasgassmann/.codex/plugins/cache/openai-primary-runtime/presentations/26.1119.11507/skills/presentations';
process.env.RUNTIME_NODE_MODULES=path.join(runtime,'node/node_modules');process.env.RUNTIME_NODE=path.join(runtime,'node/bin/node');
const read=async p=>JSON.parse(await fs.readFile(path.join(root,p),'utf8'));
const ci=await read('docs/evidence/ci/full-run.json');if(ci.exit_code!==0)throw Error('Chaîne finale non réussie');
const ml=await read('docs/evidence/mlops/evaluation.json'),load=await read('docs/evidence/k8s/load-result.json'),hpa=await read('docs/evidence/k8s/resilience-load.json'),cost=await read('docs/evidence/finops/cost-scenario.json');
const pct=x=>(x*100).toFixed(2).replace('.',',')+' %';
const slides=[
 ['Support bancaire cloud-native',['Thomas Gassmann','RNCP40875 BC3','Rédaction et sourçage assistés par IA (Codex, Claude)'], 'Sujet cloud fourni p.1-5 ; docs/rapport.md ; déclaration d’usage de l’IA en page 1 du rapport'],
 ['Objectif et couverture de la grille',['Chaîne d’exploitation prioritaire, fonctionnel limité à 4 entités','Démontré : Compose, Kubernetes test/prod, logs, alerte, scans, FinOps','CI verte sur GitHub, images sur GHCR ; apply AWS non fait'], 'Rapport p.2 ; docs/rapport.md. Domaine à faire valider par l’enseignant.'],
 ['Architecture et arbitrages',['Vue/Nginx séparé, FastAPI sans état, sessions en PostgreSQL','S3 et SQS locaux : mêmes protocoles qu’AWS, client inchangé','Prix : SeaweedFS et ElasticMQ n’ont pas la durabilité d’AWS'], 'Rapport p.3 ; docs/rapport.md, diagrammes Mermaid ; compose.yml'],
 ['Accès et chiffrement',['Propriétaire ou agent, conflits de version refusés (409)','Argon2id, sessions hachées, cookie sécurisé, CSRF et origine','Contenu chiffré AES-GCM, métadonnées en clair pour les requêtes'], 'Rapport p.4 ; docs/rapport.md ; evidence/k8s/security.json ; integration/least-privilege.json'],
 ['Parcours réel de l’application',['Ticket et pièce jointe privée','Suggestion anglaise versionnée','CSV produit par le worker'], 'docs/evidence/browser/checks.json et tickets-desktop.png ; capture de fixtures synthétiques'],
 ['Scaling et perturbations',[`${load.requests} requêtes, ${pct(load.availability_fraction)} réussies, p95 ${(1000*load.latency_p95_seconds).toFixed(0)} ms (v1.2.1) ; v1.3.0 rejouée : 100 % réussies, p95 117 ms`, 'Rolling maxUnavailable=0 ; correctif de clé : p95 680 → 74 ms'], 'Rapport p.6 ; docs/evidence/k8s/load-result.json ; resilience-load.json ; diagnosis/. Fenêtre locale avec pannes, pas SLA mensuelle.'],
 ['Supervision et restauration',['Alerte en 31 secondes, puis résolue','Logs des pods dans Loki','Sauvegarde chiffrée, 7 tables restaurées'], 'Rapport p.7 et p.10 ; capture docs/evidence/screenshots/04-grafana-exploitation-slo.png ; docs/evidence/k8s/alert-cycle.json ; backup-restore.json ; logging.json ; evidence/followup/ ; README.md'],
 ['CI et infrastructure déclarative',['Run GitHub n°9 : 5 jobs verts','Images publiées sur GHCR','Terraform AWS validé, non appliqué'], 'Rapport p.8-9 ; README.md ; .github/workflows/ci.yml ; scripts/ci/ ; capture docs/evidence/screenshots/01-github-actions-run-9.png (run 45471165207). 32 tests Compose, 32 Kubernetes, 34 hors ligne. Aucun apply AWS.'],
 ['Validation du modèle d’intention',['BANKING77 anglais, 77 intentions, test officiel réservé',`Test sélectionné : F1 macro ${ml.test_macro_f1.toFixed(4)}, top3 ${pct(ml.test_top3_accuracy)}`], 'PolyAI-LDN/task-specific-datasets révision 57ec275d8078af65b7731c2a98be812d844a6d6b, CC BY 4.0 ; evidence/mlops/. Graphique de validation arrondi à six décimales.'],
 ['Promotion et retour arrière',['Deux versions, seuil de qualité et contrôle SHA avant chargement','Candidat dégradé ou altéré refusé, rollback réellement exercé','Marges non probabilistes, confirmation humaine et compteur de version'], 'docs/evidence/mlops/registry.json ; docs/rapport.md. SHA ne remplace pas une signature de build.'],
 ['Réduction de l’image worker',['14 distributions utiles contre 45 dans l’image API partagée','Baisse initiale de 63,66 % de taille Docker non compressée'], 'docs/evidence/finops/worker-image.json. Comparaison initiale réelle, pas une baisse de RAM ou une économie financière.'],
 ['Ressources et budget',['Sondes natives : CPU moyen au repos de 0,40340 à 0,00659 cœur',`Scénario Paris : ${Number(cost.scenario_subtotal_usd).toFixed(2).replace('.',',')} USD/mois avant exclusions`,`Arbitrage : un seul NAT, moins cher mais moins disponible`], 'Rapport p.12 ; docs/evidence/finops/native-probes.json ; cost-scenario.json ; prix AWS publics datés par SKU. Avec marge 30 % : '+Number(cost.scenario_with_margin_usd).toFixed(2).replace('.',',')+' USD/mois, aucun budget approuvé. Énergie et CO2 non mesurés.'],
 ['Sécurité et contrôles ISO 27001',['v1.3.0 : aucun avis HIGH ou CRITICAL corrigeable restant','Avis HIGH sans correctif : 47 API/worker, 106 backup, à trier','Prod isolée : trafic depuis bc3-test bloqué, secrets distincts'], 'Rapport p.13 ; docs/evidence/security/followup-*.json ; evidence/environments/ ; docs/rapport.md ; correspondance Annexe A pédagogique, pas certification ISO'],
 ['Difficultés, réserves et suites',['11 difficultés corrigées et retestées : socket, latence, backup, écarts Linux de la CI…','Réserves : accord enseignant, apply AWS, certification cloud','Suites : approbation prod, cluster persistant, apply AWS'], 'Rapport p.14-15 ; docs/rapport.md']
];
const deck=Presentation.create({slideSize:{width:1280,height:720}});
function text(s,value,x,y,w,h,size=30,bold=false,color='#203746'){const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});t.text=value;t.text.style={fontFamily:'Arial',fontSize:size,bold,color};return t;}
for(let i=0;i<slides.length;i++){
 const [title,body,source]=slides[i],s=deck.slides.add();s.background.fill=i===0?'#123443':'#f7fafb';
 text(s,title,76,66,1128,i===0?170:115,i===0?64:46,true,i===0?'#ffffff':'#123443');
 if(i===4){
  body.forEach((v,j)=>text(s,v,76,240+j*105,330,90,29));const bytes=await fs.readFile(path.join(root,'docs/evidence/browser/tickets-desktop.png'));
  s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Capture réelle du parcours de support avec fixtures de test',fit:'contain',position:{left:450,top:185,width:740,height:440}});
 }else if(i===6||i===7){
  body.forEach((v,j)=>text(s,v,76,240+j*105,330,90,29));const shot=i===6?'04-grafana-exploitation-slo.png':'01-github-actions-run-9.png';const bytes=await fs.readFile(path.join(root,'docs/evidence/screenshots',shot));
  s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:i===6?'Capture Grafana du tableau de bord Exploitation et SLO pendant la charge':'Capture du run GitHub Actions n°9 avec cinq jobs verts',fit:'contain',position:{left:450,top:185,width:740,height:440}});
 }else if(i===5){
  text(s,body.join('\n'),76,182,1128,105,27);
  s.charts.add('line',{lineOptions:{smooth:false},position:{left:76,top:300,width:1128,height:310},categories:hpa.samples.map(v=>String(Math.round(v.seconds))+' s'),series:[{name:'Réplicas HPA',values:hpa.samples.map(v=>v.hpa_current),fill:'#126450',smooth:false,marker:{symbol:'circle',size:3}},{name:'API prêtes',values:hpa.samples.map(v=>v.ready_api),fill:'#25465c',smooth:false,marker:{symbol:'circle',size:3}}],hasLegend:true,xAxis:{textStyle:{fontSize:18}},yAxis:{min:0,max:4,title:'Réplicas',textStyle:{fontSize:18}},dataLabels:{showValue:false}});
 }else if(i===8){
  text(s,body.join('\n'),76,180,1128,105,27);s.charts.add('bar',{position:{left:76,top:300,width:1128,height:310},categories:['C = 0,25','C = 1'],series:[{name:'F1 macro sur validation',values:[0.880027,0.890887],fill:'#126450'}],hasLegend:false,xAxis:{textStyle:{fontSize:18}},yAxis:{min:0,max:1,title:'F1 macro sur validation',textStyle:{fontSize:18}},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0000',textStyle:{fontSize:20}}});
 }else if(i===10){
  text(s,body.join('\n'),76,180,1128,105,27);s.charts.add('bar',{position:{left:76,top:300,width:1128,height:310},categories:['Image partagée','Worker spécialisé'],series:[{name:'Mo décimaux, non compressés',values:[759.494790,275.993084],fill:'#126450'}],hasLegend:false,xAxis:{textStyle:{fontSize:18}},yAxis:{min:0,max:800,title:'Mo décimaux',textStyle:{fontSize:18}},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0',textStyle:{fontSize:20}}});
 }else body.forEach((v,j)=>text(s,v,76,(i===0?295:230)+j*112,1128,92,i===0?32:30,false,i===0?'#d8e8e4':'#203746'));
 text(s,`${i+1} / ${slides.length}   Thomas Gassmann   BC3`,76,660,1128,26,16,false,i===0?'#d8e8e4':'#506573');s.speakerNotes.text='Sources : '+source+'\nPrécision : preuves locales, aucune publication, dépense ni validation humaine inventée. Rédaction et sourçage assistés par IA (Codex, Claude).';
}
const build=path.join(root,'tmp/deck-build');await fs.mkdir(build,{recursive:true});await fs.mkdir(path.join(root,'output/presentations'),{recursive:true});
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(deck)).save(candidate);
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
// Polices de tous les graphiques explicites avant l’export final.
for(const s of deck.slides.items)for(const c of s.charts.items)applyPresentationChartFont(c,{fontFamily:'Arial'});
await(await PresentationFile.exportPptx(deck)).save(candidate);
const final=process.env.BC3_DECK_OUTPUT||path.join(root,'output/presentations/soutenance-bc3-thomas-gassmann.pptx');
await fs.mkdir(path.dirname(final),{recursive:true});
const validation=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:final,pythonExecutable:path.join(runtime,'python/bin/python'),integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:14,requiredNativeChartOwnerSlides:[6,9,11],requiredNativeTableOwnerSlides:[],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation-'+path.basename(final)+'.json')});
const rendered=await PresentationFile.importPptx(await FileBlob.load(final));
for(let i=0;i<rendered.slides.items.length;i++){const png=await rendered.export({slide:rendered.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));}
await fs.writeFile(path.join(root,'docs/presentation-content.json'),JSON.stringify(slides,null,2)+'\n');console.log(JSON.stringify({slides:14,final,validation}));
