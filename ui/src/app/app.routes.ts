import { Routes } from '@angular/router';

import { AuditComponent } from './features/audit/audit.component';
import { CreateAudiobookComponent } from './features/create-audiobook/create-audiobook.component';
import { PronunciationsComponent } from './features/pronunciations/pronunciations.component';
import { VoiceSamplesComponent } from './features/voice-samples/voice-samples.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'create-audiobook' },
  { path: 'create-audiobook', component: CreateAudiobookComponent },
  { path: 'audit', component: AuditComponent },
  { path: 'pronunciations', component: PronunciationsComponent },
  { path: 'voice-samples', component: VoiceSamplesComponent }
];
