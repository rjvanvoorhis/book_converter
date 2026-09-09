import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../environments/environment';
import { AudioCleanerOption, VoiceSampleSourceProbe, VoiceSampleSummary } from './models';

export interface CreateVoiceSampleRequest {
  source_path: string;
  start_seconds: number;
  end_seconds: number;
  output_folder: string;
  name: string;
  clean: boolean;
  cleaner: string;
  trim_silence: boolean;
  normalize_loudness: boolean;
}

export interface CreateVoiceSampleTask {
  task_id: string;
}

@Injectable({ providedIn: 'root' })
export class VoiceSampleApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  probeSource(path: string): Observable<VoiceSampleSourceProbe> {
    const params = new HttpParams().set('path', path);
    return this.http.get<VoiceSampleSourceProbe>(`${this.baseUrl}/voice-samples/source`, {
      params
    });
  }

  /** URL for the whole raw source recording, for scrubbing in a normal player. */
  getSourceAudioUrl(path: string): string {
    return `${this.baseUrl}/voice-samples/source/audio?path=${encodeURIComponent(path)}`;
  }

  /** URL for an unprocessed preview of [start, end) of the source recording,
   * so a candidate clip can be auditioned before it's cleaned and saved. */
  getSourceClipUrl(path: string, startSeconds: number, endSeconds: number): string {
    const params = new HttpParams()
      .set('path', path)
      .set('start', startSeconds)
      .set('end', endSeconds);
    return `${this.baseUrl}/voice-samples/source/clip?${params.toString()}`;
  }

  listCleaners(): Observable<AudioCleanerOption[]> {
    return this.http
      .get<{ cleaners: AudioCleanerOption[] }>(`${this.baseUrl}/voice-samples/cleaners`)
      .pipe(map((response) => response.cleaners));
  }

  listSamples(folder: string): Observable<VoiceSampleSummary[]> {
    const params = new HttpParams().set('folder', folder);
    return this.http
      .get<{ samples: VoiceSampleSummary[] }>(`${this.baseUrl}/voice-samples/library`, {
        params
      })
      .pipe(map((response) => response.samples));
  }

  getSampleAudioUrl(path: string): string {
    return `${this.baseUrl}/voice-samples/audio?path=${encodeURIComponent(path)}`;
  }

  // A model-based cleaner can take the better part of a minute (loading a
  // neural net and running a forward pass on CPU), so this follows the
  // task/poll pattern like every other TTS-adjacent action rather than
  // returning the sample directly.
  createSample(request: CreateVoiceSampleRequest): Observable<CreateVoiceSampleTask> {
    return this.http.post<CreateVoiceSampleTask>(`${this.baseUrl}/voice-samples`, request);
  }

  deleteSample(path: string): Observable<void> {
    const params = new HttpParams().set('path', path);
    return this.http.delete<void>(`${this.baseUrl}/voice-samples`, { params });
  }
}
