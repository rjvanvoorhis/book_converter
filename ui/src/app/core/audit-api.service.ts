import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  ApplyEditsResult,
  ArtifactCut,
  AudiobookSummary,
  AudiobookTaskState,
  CreateAudiobookTask,
  DetectArtifactsResult,
  PendingEdits,
  ResegmentTranscriptResult,
  ReviewState,
  ReviewStatus,
  StageCutRequest,
  StageRegenerationRequest,
  StageRegenerationResult,
  Transcript
} from './models';

@Injectable({ providedIn: 'root' })
export class AuditApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  listAudiobooks(audiobookFolder: string): Observable<AudiobookSummary[]> {
    const params = new HttpParams().set('audiobook_folder', audiobookFolder);
    return this.http
      .get<{ audiobooks: AudiobookSummary[] }>(`${this.baseUrl}/audiobooks/library`, {
        params
      })
      .pipe(map((response) => response.audiobooks));
  }

  getTranscript(path: string): Observable<Transcript> {
    const params = new HttpParams().set('path', path);
    return this.http.get<Transcript>(`${this.baseUrl}/audiobooks/transcript`, { params });
  }

  getAudioUrl(path: string): string {
    return `${this.baseUrl}/audiobooks/audio?path=${encodeURIComponent(path)}`;
  }

  /** URL for just [start, end) of the audiobook, decoded on demand server-side.
   * Used by the segment player so it never has to load the whole file. */
  getClipUrl(path: string, startSeconds: number, endSeconds: number): string {
    const params = new HttpParams()
      .set('path', path)
      .set('start', startSeconds)
      .set('end', endSeconds);
    return `${this.baseUrl}/audiobooks/clip?${params.toString()}`;
  }

  getReview(path: string): Observable<ReviewState> {
    const params = new HttpParams().set('path', path);
    return this.http.get<ReviewState>(`${this.baseUrl}/audiobooks/review`, { params });
  }

  setReviewStatus(
    path: string,
    segmentIndex: number,
    status: ReviewStatus,
    note?: string
  ): Observable<ReviewState> {
    return this.http.post<ReviewState>(`${this.baseUrl}/audiobooks/review`, {
      path,
      segment_index: segmentIndex,
      status,
      note
    });
  }

  /** Cuts from the most recent completed scan, persisted server-side so
   * they survive a reload instead of only living in component state. */
  getArtifacts(path: string): Observable<ArtifactCut[]> {
    const params = new HttpParams().set('path', path);
    return this.http
      .get<{ cuts: ArtifactCut[] }>(`${this.baseUrl}/audiobooks/artifacts`, { params })
      .pipe(map((response) => response.cuts));
  }

  detectArtifacts(path: string): Observable<CreateAudiobookTask> {
    return this.http.post<CreateAudiobookTask>(`${this.baseUrl}/audiobooks/artifact-scans`, {
      path
    });
  }

  /** Splits any transcript segment over the merge cap back into several
   * smaller segments, in place. Pure text processing plus one JSON write -
   * fast even on a long book, so this is a plain request/response, not the
   * task/poll pattern used for TTS work. */
  resegmentTranscript(path: string): Observable<ResegmentTranscriptResult> {
    return this.http.put<ResegmentTranscriptResult>(`${this.baseUrl}/audiobooks/transcript`, {
      path
    });
  }

  /** Every staged edit for a book, keyed by segment index - empty until the
   * user stages anything. Persisted server-side (see pending_edit_store),
   * so it survives a reload. */
  getEdits(path: string): Observable<PendingEdits> {
    const params = new HttpParams().set('path', path);
    return this.http
      .get<{ edits: PendingEdits }>(`${this.baseUrl}/audiobooks/edits`, { params })
      .pipe(map((response) => response.edits));
  }

  /** URL for a staged regeneration's actual generated audio - this is the
   * real take, not a disposable preview, so it can just be played directly
   * from disk rather than fetched through the task blob store. */
  getEditAudioUrl(path: string, segmentIndex: number): string {
    const params = new HttpParams().set('path', path).set('segment_index', segmentIndex);
    return `${this.baseUrl}/audiobooks/edits/audio?${params.toString()}`;
  }

  /** Synthesizes the real replacement audio for one segment and stages it -
   * there's no separate throwaway "preview" step. Runs through the
   * task/poll pattern like every TTS call in this API; once complete, the
   * result is on disk and playable via getEditAudioUrl. */
  stageRegeneration(request: StageRegenerationRequest): Observable<CreateAudiobookTask> {
    return this.http.post<CreateAudiobookTask>(
      `${this.baseUrl}/audiobooks/edits/regenerations`,
      request
    );
  }

  /** Stages a [start, end) range of a segment's own audio to be dropped -
   * just a manifest write, no ffmpeg work yet, so unlike every TTS-backed
   * action this is a plain synchronous request. */
  stageCut(request: StageCutRequest): Observable<PendingEdits> {
    return this.http
      .post<{ edits: PendingEdits }>(`${this.baseUrl}/audiobooks/edits/cuts`, request)
      .pipe(map((response) => response.edits));
  }

  /** Drops a staged edit without applying it. */
  discardEdit(path: string, segmentIndex: number): Observable<PendingEdits> {
    const params = new HttpParams().set('path', path).set('segment_index', segmentIndex);
    return this.http
      .delete<{ edits: PendingEdits }>(`${this.baseUrl}/audiobooks/edits`, { params })
      .pipe(map((response) => response.edits));
  }

  /** Bakes every staged edit into the real audiobook file in one pass, no
   * full re-encode of the book - see audit_service.apply_pending_edits.
   * Rebuilding around N edits still takes real time, so this follows the
   * same task/poll pattern as detection. */
  applyEdits(path: string): Observable<CreateAudiobookTask> {
    return this.http.post<CreateAudiobookTask>(`${this.baseUrl}/audiobooks/edits/apply`, {
      path
    });
  }
}

export type DetectTaskState = AudiobookTaskState<DetectArtifactsResult>;
export type StageRegenerationTaskState = AudiobookTaskState<StageRegenerationResult>;
export type ApplyEditsTaskState = AudiobookTaskState<ApplyEditsResult>;
