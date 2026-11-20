# Gebruikershandleiding — Catalogus-editor

[English](guide.en.md) · [Français](guide.fr.md) · [Deutsch](guide.de.md) · [Español](guide.es.md) · [Italiano](guide.it.md) · **Nederlands** · [Polski](guide.pl.md) · [Português](guide.pt.md)

De catalogus-editor is een Home Assistant-kaart waarmee u de items van de ReefTech-catalogi (apparatuur, supplementen…), van de huisweergave (bomen, objecten) en van ReefTank (vissen, koralen, planten, ongewervelden) kunt **bekijken, bewerken en aanmaken**, en ze vervolgens aan de community kunt **voorstellen**.

## 1. Waar dient de editor voor?

Stel u een kaartenbak voor: één kaart per verwarming, supplement, vis of boom. De editor is de kaart waarmee u ze leest, er een verbetert of een nieuwe toevoegt, rechtstreeks vanuit uw dashboard, zonder een bestand aan te raken.

Drie dingen om te onthouden:

1. **Wat u opslaat, is meteen bruikbaar** bij u thuis: het item komt in uw ‘gebruikerslaag’, die alle integraties delen die de catalogus lezen.
2. **Het aan de catalogus voorstellen is een extra, optionele stap**: de editor opent voor u een *pull request* (een verzoek tot opname) op GitHub, zodat uw item iedereen helpt.
3. **De editor controleert uw items** met dezelfde regels als de catalogus: zegt hij ‘Everything checks out’, dan wordt het item geaccepteerd.

## 2. Voor u begint

### De kaart installeren en toevoegen

1. Installeer de integratie *Catalog editor* (aangepaste HACS-repository, of kopieer de map `custom_components/catalog_editor`) en voeg haar toe via *Instellingen → Apparaten en diensten*.
2. De integratie vraagt om de **client-ID van een GitHub OAuth-app** (zie hieronder) en om de **catalogi waarop u zich abonneert** (apparatuur, supplementen, parameters, watertests, bomen, objecten en de ReefTank-soorten: vissen, koralen, planten, ongewervelden). Standaard is alles aangevinkt; later te wijzigen onder *Configureren*.
3. Voeg op een dashboard een handmatige kaart toe met deze code:

```yaml
type: custom:catalog-editor-card
```

De integratie levert de kaart zelf: er hoeft niets aan de resources te worden toegevoegd. Ze verschijnt in het Frans of Engels, afhankelijk van de taal van Home Assistant.

### De GitHub-app aanmaken (eenmalig, 1 minuut)

Deze stap is alleen nodig als u items aan de catalogus wilt **voorstellen**. Om thuis te bewerken kunt u hem overslaan.

1. Open <https://github.com/settings/applications/new> (ingelogd bij GitHub).
2. *Application name*: wat u wilt, bijvoorbeeld `Catalog editor`. *Homepage URL* en *Authorization callback URL*: een willekeurig adres, bijvoorbeeld `https://github.com/Elwinmage/catalog-editor` (ze worden niet gebruikt).
3. Vink **Enable Device Flow** aan en kies **Register application**.
4. Kopieer de **Client ID** van de volgende pagina naar de integratie. Een geheim is niet nodig.

## 3. Eerste start: een catalogus downloaden

De eerste keer staat een catalogus nog niet op uw Home Assistant. De kaart meldt het: *‘This catalog is not downloaded yet’*.

![Catalogus niet gedownload: de knop Download (1) en de catalogus-lijst (2)](img/en/01-download.png)

1. Klik op **Download** (1): de kaart haalt de laatst gepubliceerde versie van de catalogus op.
2. Om van catalogus te wisselen, opent u bovenaan de **keuzelijst** (2). Achter elke naam staat de familie: *(reeftech)*, *(reeftank)* of *(house view)*.

De gedownloade catalogus wordt gedeeld met de andere geïnstalleerde integraties: één download voor iedereen. Later haalt **Check for updates** een nieuwere versie op.

> Ontbreekt een catalogus in de lijst, dan bent u er niet op geabonneerd. Voeg hem toe onder *Configureren* bij de integratie.

## 4. Rondleiding over het scherm

Dit is het beginscherm. De rode markeringen komen overeen met de lijst hieronder.

![Beginscherm van de editor, genummerd van 1 tot 5](img/en/02-home.png)

1. **De catalogus**: de keuzelijst bepaalt welke u bekijkt.
2. **Het soort item**: een catalogus bevat er meerdere (hier Items, Categories, Tasks).
3. **Zoeken**: typ een paar letters, de lijst wordt meteen korter.
4. **+ New**: maakt een leeg item.
5. **Check for updates**: haalt een nieuwe versie van de catalogus op.

Onder de lijst gaan twee gebieden over GitHub: de **verbinding** en uw **pull requests** (paragraaf 8 en 9). Elke rij heeft een label: *catalog* voor een officieel item, *yours* voor een item dat u thuis hebt opgeslagen.

## 5. Een item terugvinden

- **Met zoeken**: typ een deel van de naam of de id. Komt niets overeen, dan toont de kaart ‘Nothing here yet’.
- **Op merk**: in de apparatuurcatalogus zijn de items gegroepeerd (Eheim, Tunze, zonder merk…). Klik op het pijltje van een groep om hem te openen.
- **Op watertype**: in de ReefTank-soortencatalogi — **vissen, koralen, planten en ongewervelden** — filteren knoppen de lijst: *All waters*, *Marine*, *Freshwater*, *Brackish*. Het getal tussen haakjes is het aantal items.

![Vissenlijst gefilterd op Marine](img/en/03-water-filter.png)

Planten en ongewervelden vindt u op precies dezelfde manier:

![Plantencatalogus, met zijn watertype-filter](img/en/04-plants.png)

Klik gewoon op een rij om een item te openen.

## 6. Een item bewerken of aanmaken

Het formulier wordt gegenereerd uit de regels van de catalogus: een veld dat aan de catalogus wordt toegevoegd, verschijnt hier zonder update van de kaart.

- Velden met een **rode ster** zijn verplicht.
- Bij een item **uit de catalogus** herinnert een banner u eraan dat opslaan **uw eigen versie** aanmaakt: het origineel wordt nooit gewijzigd.
- **Identifier**: automatisch voorgesteld (kleine letters, cijfers, `-` en `_`). Bij een soort is het de wetenschappelijke naam (`geslacht_soort`). U kunt hem aanpassen.
- **Namen in meerdere talen**: vul minstens het Engels in. *Other languages* klapt de rest open; de knop **Translate** vult de ontbrekende talen voor u in.
- **Vakjes en lijsten**: watertypes, rifveilig… afhankelijk van het item. Een kleur (bomen, objecten) kiest u met de kleurkiezer of typt u als `#rrggbb`.

Onder het formulier meldt een bericht de toestand van het item: **‘Everything checks out’** in het groen, of de lijst met wat gecorrigeerd moet worden. Zolang er een fout is, zijn de opslagknoppen grijs.

### Wat verschilt per catalogus

| Catalogus | Afbeelding van het item |
| --- | --- |
| Apparatuur, supplementen, parameters, watertests, bomen, objecten | Een blok **Image** laat u een afbeelding uploaden (omgezet naar transparant WebP) |
| **Vissen** | Geen afbeelding om te uploaden: u bouwt een **animatie** (paragraaf 7) |
| **Koralen, planten, ongewervelden** | De editor bewerkt de **beschrijving** van de soort. De afbeeldingen worden gemaakt met de hulpmiddelen van de ReefTank-catalogus (zie de README): dit formulier heeft geen fotoblok |

![Formulier van een plant: alleen de beschrijving, geen fotoblok](img/en/05-plant-form.png)

## 7. Vissen: foto en animatie

In het aquarium van ha-reef-card kan een vis op **drie weergaveniveaus** worden getoond. Dit is de sleutel om te begrijpen wat de editor doet:

| Niveau | Wat u ziet | Waar het vandaan komt |
| --- | --- | --- |
| **1. Algemene vis** | Een standaardvis, dezelfde voor alle betrokken soorten | Geen afbeelding in het item: dit is de standaard van de catalogus (`unknown_fish`) |
| **2. Animatie uit een foto** (‘degraded’) | De echte vis, met een eenvoudige animatie: zwemmen, rusten, keren | **Door de editor gebouwd** uit een foto (door AI gegenereerd of uw eigen) |
| **3. Animatie uit video's** (‘real’) | De echte vis, met een vloeiende, natuurlijke animatie | **Buiten de editor** gebouwd, met de hulpmiddelen van de ReefTank-catalogus, uit korte videoclips (Kling, Veo…) |

De editor brengt een soort dus snel en zonder video van niveau 1 naar niveau 2. Niveau 3 blijft het einddoel: als het bestaat, **wordt het nooit vervangen** door een animatie uit een foto, tenzij u *‘Use it anyway (ignore the checks)’* aanvinkt. Omgekeerd is een animatie van niveau 2 bedoeld om ooit door een echte te worden vervangen.

Het blok *Photo and animation* toont altijd de stand van zaken: *‘This species has no picture yet’* (niveau 1), *‘Its animation was made from a photo…’* (niveau 2) of *‘Its animation was made from videos: a photo does not replace it’* (niveau 3).

### Stap 1 — De foto voorbereiden

Het blok *Photo and animation* staat onder het soortformulier. De rode markeringen komen overeen met:

![Blok Photo and animation, genummerd van 1 tot 6](img/en/07-photo-block.png)

1. **Species in the prompt**: de wetenschappelijke naam waarmee de afbeelding wordt gevraagd (voor u ingevuld).
2. **Background colour**: magenta of groen. Kies de kleur die het meest contrasteert met de soort (geen magenta voor een roze vis).
3. **Show the prompt**: toont de exacte tekst die wordt verzonden, zodat u hem in een ander beeldprogramma kunt gebruiken.
4. **Generate the photo**: vraagt de afbeelding aan bij uw AI-aanbieder. Kies eerst de aanbieder (Google Gemini, OpenAI of Cloudflare Workers AI) en voer **uw eigen API-sleutel** in bij de *Opties* van de integratie. De sleutel blijft in Home Assistant en wordt nooit naar de kaart teruggestuurd. Zonder sleutel verschijnt deze knop niet.
5. **Uw eigen foto**: u kunt ook een bestand uploaden (PNG, JPEG of WebP). Geef dan de maker en de licentie op.
6. **Play the animation**: opent het voorbeeld (stap 3). Deze knop verschijnt alleen als het item al een animatie heeft of u er net een hebt gebouwd.

De foto moet **één vis van opzij, kop naar rechts**, op een egale achtergrond tonen.

### Stap 2 — De foto controleren en de animatie bouwen

Eenmaal gegenereerd verschijnt de foto als miniatuur met zijn herkomst (gebruikt model, afmetingen). De editor **controleert** hem: egale achtergrond, hele vis niet afgesneden door de rand, groot genoeg. Wordt hij geweigerd, dan legt de kaart uit waarom: genereer opnieuw of wijzig de achtergrondkleur.

![Gegenereerde foto, met herkomst, en de knop Build the animation](img/en/08-photo-generated.png)

Wordt de foto geaccepteerd, klik dan op **Build the animation**. Het bericht *‘Animation ready: it is attached when you save the entry’* bevestigt dat alles goed is.

### Stap 3 — De animatie bekijken

**Play the animation** opent een paneel naast het formulier. Het herhaalt vier reeksen: **stay** (stilstaan), **swim** (zwemmen), **turn** (keren) en daarna de keer **gespiegeld**, zodat de vis weer in zijn beginrichting kijkt. De naam van de lopende reeks staat boven de vis. *Close* sluit het paneel.

Met de lijst **Background** beoordeelt u het resultaat op drie achtergronden: **Water**, **Dark** en **Light**.

![Het voorbeeld op de drie achtergronden: Water, Dark, Light](img/en/09-preview-backgrounds.png)

> De schermafbeeldingen in deze handleiding tonen een voor het voorbeeld getekende vis: de echte animatie volgt de foto van uw soort.

## 8. Opslaan en aan de catalogus voorstellen

### Thuis opslaan

**Save** zet het item in uw gebruikerslaag, gedeeld door alle integraties: het is **meteen** bruikbaar, zonder te wachten op een release. Bij een item uit de catalogus is het een lokale kopie (een *override*): ze behoudt de oorspronkelijke afbeelding totdat u een nieuwe uploadt.

### Verbinden met GitHub (eenmalig)

1. Klik op **Connect to GitHub** in het GitHub-gedeelte.
2. De kaart toont een **code** (zoals `ABCD-1234`) en een GitHub-adres.
3. Open het adres, typ de code en bevestig.
4. De kaart merkt de verbinding zelf op en toont *‘Connected as …’*.

![GitHub-aanmeldcode getoond door de kaart](img/en/10-github-code.png)

De editor vraagt alleen om de toestemming `public_repo`: hij maakt een fork van de catalogus, pusht een branch en opent de pull request. Het token blijft opgeslagen in Home Assistant. **Disconnect** wist het.

### Voorstellen

1. Controleer of het bericht **‘Everything checks out’** meldt.
2. Vink het **certificeringsvakje** aan: u verklaart dat elke afbeelding uw eigen werk is (of dat u de rechten bezit) en gaat akkoord met publicatie onder CC BY 4.0.
3. Klik op **Save and propose to the catalog**. De knop blijft grijs zolang u niet bent verbonden, het item een fout heeft of het vakje niet is aangevinkt.

![Item klaar om voor te stellen: Save (1) en Save and propose to the catalog (2)](img/en/11-propose.png)

De kaart toont dan het nummer van de geopende pull request. Slaat u opnieuw op terwijl hij open is, dan wordt er een commit aan toegevoegd. Bij een vis bevat het verzoek de animatie en het miniatuur, **nooit de foto**.

**Propose all my entries** verstuurt in één keer al uw lokale items die nog niet zijn voorgesteld. Horen ze bij meerdere catalogi, dan wordt per repository één pull request geopend.

## 9. Uw pull requests volgen

Onderaan de kaart toont **Your pull requests** wat u hebt voorgesteld. Vier knoppen filteren de lijst (het getal geeft het aantal verzoeken):

![Lijst van pull requests en de vier filters](img/en/12-pull-requests.png)

| Filter | Wat het toont |
| --- | --- |
| Open | Verzoeken die op beoordeling wachten (standaardweergave) |
| Merged | Geaccepteerd, maar nog niet in een gepubliceerde versie van de catalogus |
| In the catalog | Geaccepteerd en in een versie gepubliceerd |
| All | Alles, ook geweigerde verzoeken (met een label gemarkeerd) |

Klik op het nummer van een verzoek om het op GitHub te openen. **Refresh** laadt de lijst opnieuw.

Zodra uw verzoek is samengevoegd **en** uitgebracht, wordt uw lokale kopie automatisch verwijderd als ze identiek is aan het item van de catalogus. Anders blijft ze staan: verwijder haar met de hand vanuit het item.

## 10. Veelgestelde vragen

| Symptoom | Waarschijnlijke oorzaak | Wat te doen |
| --- | --- | --- |
| Een catalogus ontbreekt in de lijst | U bent er niet op geabonneerd | *Configureren* bij de integratie, vink hem aan (ze herlaadt) |
| Er is geen knop ‘Generate the photo’ | Geen beeldaanbieder ingesteld | Kies een aanbieder en voer uw sleutel in bij de opties; of upload uw eigen foto |
| De foto wordt geweigerd | Achtergrond niet egaal, vis afgesneden of te klein | Genereer opnieuw of wijzig de achtergrondkleur |
| Een animatie kan niet worden vervangen | Het item heeft al een animatie uit video's (niveau 3) | Dat is de bedoeling. Vink *‘Use it anyway’* alleen aan als u zeker bent |
| ‘Save and propose’ is grijs | Niet verbonden, fout in het item of certificering niet aangevinkt | Corrigeer het item, verbind, vink het vakje aan |
| De GitHub-aanmelding is verlopen | Token ingetrokken of verlopen | Klik opnieuw op *Connect to GitHub*; het lopende voorstel gaat na het inloggen verder |
| De kaart werkt niet bij | Browsercache | Laad de pagina opnieuw (Ctrl+F5); meerdere keren verversen kan nodig zijn |

Een item dat u opslaat is een **lokale kopie**: om het te verwijderen opent u het en gebruikt u de knop voor verwijderen.
