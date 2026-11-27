<p align="center"><img src="https://raw.githubusercontent.com/EduWISP/.github/main/branding/eduwisp-mark.svg" alt="EduWISP" height="72"></p>

# eduwisp-apps

**Gestione applicazioni** · *Application management*

Catalogo app EduWISP **multipiattaforma** (oggi APK Android firmati, sul modello di F-Droid; domani pacchetti di altre piattaforme), assegnazioni e configurazioni gestite.

> 🧪 **Stato: prototipo v0.** **App consentite** ([ADR-0019](https://eduwisp.org/docs/decisioni/0019-app-consentite/)): catalogo dell'istituto, elenco per istituto, indirizzo e classe, sblocchi temporanei dei docenti. Il catalogo di APK firmati è ancora in progettazione ([documentazione](https://eduwisp.org/docs/moduli/android/)).

## App consentite / App allowlist

- **Catalogo dell'istituto**: nome e identificativo dell'app (per Android il nome del pacchetto).
- **App consentite** per tutto l'istituto, per un indirizzo o per una classe: i livelli si sommano.
- **Elenco attivo** solo quando l'istituto lo attiva (`AppPolicyState`): da quel momento sui tablet le altre app con icona vengono sospese.
- **Sblocco temporaneo**: un docente sblocca un'app del catalogo per una delle sue classi, al massimo per 4 ore; la policy porta la scadenza, così il tablet richiude l'app anche senza rete. Sblocchi e richiusure anticipate sono registrati in eduwisp-audit.
- **Catalogo della piattaforma**, gestito solo dall'amministratore di sistema: app **consentite in tutti gli istituti** (istruzione, ufficio, comunicazione: per esempio Classroom, Teams, MyLIM, WhatsApp) e app **vietate ovunque** (social, incontri, VPN, Tor, browser con VPN integrata). Le vietate sono bloccate anche negli istituti che non usano l'elenco di app consentite, e nessuno le può consentire o sbloccare.
- **Elenco unico con la spunta «obbligatoria»** ([ADR-0020](https://eduwisp.org/docs/decisioni/0020-app-obbligatorie/)): ogni app consentita può essere obbligatoria per tutti, per un indirizzo o per una classe, e avere il suo **logo**. Se nel catalogo c'è l'**APK** (app libera o fornito dall'editore), il tablet la **installa da solo** appena registrato, verificando l'impronta SHA-256; altrimenti la propone allo studente con il pulsante «Installa». Gli APK non sono pubblici: li scaricano solo i tablet dell'istituto per cui l'app è obbligatoria.
- Si collega a eduwisp-devices come contributo alla policy:

```python
EDUWISP_POLICY_PROVIDERS = ["eduwisp_apps.policy.provide"]
EDUWISP_PUBLIC_URL = "https://eduwisp.scuola.example"  # per gli indirizzi di logo e APK
EDUWISP_PRIVATE_MEDIA_ROOT = "/var/lib/eduwisp/privato"  # APK, non serviti da nginx
# urls.py: path("", include("eduwisp_apps.urls"))
```

🇬🇧 ***Multi-platform** EduWISP app catalogue (signed Android APKs first, F-Droid-like; other platforms' packages later), assignments and managed configurations. **Status: prototype v0**: app allowlist per school, track and class, with audited temporary unlocks by teachers (ADR-0019). See the [design docs](https://eduwisp.org/docs/en/modules/android/).*

## Documentazione / Documentation

- Progettazione / Design: <https://eduwisp.org/docs/moduli/android/>
- Mappa dei repository / Repository map: <https://eduwisp.org/docs/architettura/repository/>
- Documentazione del modulo / Module docs: [`docs/user/`](docs/user/) · [`docs/developer/`](docs/developer/)

## Dipendenze / Dependencies

[`eduwisp-utils`](https://github.com/EduWISP/eduwisp-utils), [`eduwisp-users`](https://github.com/EduWISP/eduwisp-users), [`eduwisp-audit`](https://github.com/EduWISP/eduwisp-audit), [`eduwisp-devices`](https://github.com/EduWISP/eduwisp-devices)

## Privacy

Dati personali previsti e regole: [PRIVACY.md](PRIVACY.md). Il rispetto della normativa su privacy e minori è un vincolo bloccante ([ADR-0008](https://eduwisp.org/docs/decisioni/0008-conformita-normativa/)).

## Responsabile del modulo / Module owner

Cerchiamo persone che vogliano prendere in carico questo modulo! Proponiti in [Discussions](https://github.com/EduWISP/docs/discussions). / *Want to own this module? Say hi in Discussions.*

## Contribuire / Contributing

Vedi [CONTRIBUTING](https://github.com/EduWISP/.github/blob/main/CONTRIBUTING.md) e il [Codice di condotta](https://github.com/EduWISP/.github/blob/main/CODE_OF_CONDUCT.md). **Mai dati personali reali** di studenti, famiglie o personale.

## Licenza / License

**AGPL-3.0-or-later**, con termini aggiuntivi di attribuzione e tutela del nome (sezione 7): vedi [LICENSE](LICENSE) e [NOTICE.md](NOTICE.md). Chi usa o modifica EduWISP deve sempre indicare «Basato su EduWISP» e non può usare il nome e il logo per versioni modificate. Licenza scelta secondo le [linee guida AgID](https://eduwisp.org/docs/decisioni/0006-licenza/) per il software usato via rete.

*AGPL-3.0-or-later with additional attribution and trademark terms (section 7): see LICENSE and NOTICE.md.*

I contributi richiedono il [DCO](https://github.com/EduWISP/.github/blob/main/CONTRIBUTING.md#dco) (`git commit -s`).
