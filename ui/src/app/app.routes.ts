import { Routes } from '@angular/router';

import { AuditComponent } from './features/audit/audit.component';
import { CreateAudiobookComponent } from './features/create-audiobook/create-audiobook.component';
import { EbooksComponent } from './features/ebooks/ebooks.component';
import { OrganizationComponent } from './features/organization/organization.component';
import { PronunciationsComponent } from './features/pronunciations/pronunciations.component';
import { TextExtractionComponent } from './features/text-extraction/text-extraction.component';
import { VoiceSamplesComponent } from './features/voice-samples/voice-samples.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'create-audiobook' },
  { path: 'extract-text', component: TextExtractionComponent },
  { path: 'create-audiobook', component: CreateAudiobookComponent },
  { path: 'ebooks', component: EbooksComponent },
  { path: 'audit', component: AuditComponent },
  { path: 'organization', component: OrganizationComponent },
  { path: 'pronunciations', component: PronunciationsComponent },
  { path: 'voice-samples', component: VoiceSamplesComponent }
];
