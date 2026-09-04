import { Component, ElementRef, OnInit, ViewChild, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AudiobookApiService } from '../../core/audiobook-api.service';
import {
  ApplyEditsTaskState,
  AuditApiService,
  DetectTaskState,
  StageRegenerationTaskState
} from '../../core/audit-api.service';
import { PronunciationApiService } from '../../core/pronunciation-api.service';
import {
  DEFAULT_AUDIOBOOK_FOLDER,
  DEFAULT_PRONUNCIATIONS_FOLDER,
  TTS_PROVIDERS
} from '../../core/constants';
import {
  AudiobookSummary,
  ArtifactCut,
  PendingEdits,
  PronunciationDictSummary,
  ReviewState,
  ReviewStatus,
  Transcript,
  TranscriptSegment,
  VoiceProfile
} from '../../core/models';

// A merged narration segment can run many minutes long; jumping to a
// flagged noise artifact plays just this much context on either side of it,
// not the whole segment.
const _FLAGGED_CLIP_PADDING_SECONDS = 10;

@Component({
  selector: 'app-audit',
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: './audit.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './audit.component.css'
})
export class AuditComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly api = inject(AuditApiService);
  private readonly voiceApi = inject(AudiobookApiService);
  private readonly pronunciationApi = inject(PronunciationApiService);

  @ViewChild('player') playerRef?: ElementRef<HTMLAudioElement>;

  readonly ttsProviders = TTS_PROVIDERS;
  readonly pronunciationDicts = signal<PronunciationDictSummary[]>([]);

  readonly folder = this.formBuilder.nonNullable.control(DEFAULT_AUDIOBOOK_FOLDER);

  readonly audiobooks = signal<AudiobookSummary[]>([]);
  readonly audiobooksLoading = signal(false);
  readonly audiobooksError = signal<string | null>(null);

  readonly selected = signal<AudiobookSummary | null>(null);
  readonly transcript = signal<Transcript | null>(null);
  readonly transcriptError = signal<string | null>(null);
  readonly review = signal<ReviewState>({ segments: {} });

  readonly detectTask = signal<DetectTaskState | null>(null);
  readonly detectTaskId = signal<string | null>(null);
  readonly cuts = signal<ArtifactCut[]>([]);
  readonly showOnlyFlagged = signal(false);

  readonly resegmenting = signal(false);
  readonly resegmentMessage = signal<string | null>(null);
  readonly resegmentError = signal<string | null>(null);

  readonly voices = signal<VoiceProfile[]>([]);
  readonly voicesLoading = signal(false);

  // Edits accumulate here - staged (a real regenerated take already
  // synthesized and saved server-side, or a [start, end) cut range) - and
  // stay staged until "Apply N edit(s)" bakes all of them into the
  // audiobook in one pass. Nothing here touches the real file yet.
  readonly edits = signal<PendingEdits>({});
  readonly openEditors = signal<Set<number>>(new Set());
  readonly editedText = signal<Record<number, string>>({});
  readonly cutRanges = signal<Record<number, { start: number; end: number }>>({});

  readonly stagingIndex = signal<number | null>(null);
  readonly stageTask = signal<StageRegenerationTaskState | null>(null);
  readonly stageError = signal<string | null>(null);

  readonly stagingCutIndex = signal<number | null>(null);
  readonly stageCutError = signal<string | null>(null);

  readonly applyTask = signal<ApplyEditsTaskState | null>(null);
  readonly applyTaskId = signal<string | null>(null);
  readonly applyError = signal<string | null>(null);

  readonly editForm = this.formBuilder.nonNullable.group({
    ttsProvider: ['pocket-tts', Validators.required],
    engine: ['pocket-tts', Validators.required],
    voice: ['', Validators.required],
    dialogueVoice: [''],
    pronunciations: [''],
    addPauses: [false]
  });

  ngOnInit(): void {
    this.loadAudiobooks();
    this.loadVoices();
    this.pronunciationApi.listDictionaries(DEFAULT_PRONUNCIATIONS_FOLDER).subscribe({
      next: (dicts) => this.pronunciationDicts.set(dicts)
    });
  }

  loadAudiobooks(): void {
    this.audiobooksLoading.set(true);
    this.audiobooksError.set(null);
    this.api.listAudiobooks(this.folder.value).subscribe({
      next: (audiobooks) => {
        this.audiobooksLoading.set(false);
        this.audiobooks.set(audiobooks);
      },
      error: (err) => {
        this.audiobooksLoading.set(false);
        this.audiobooksError.set(_errorMessage(err));
      }
    });
  }

  loadVoices(): void {
    const { engine, ttsProvider } = this.editForm.getRawValue();
    this.voicesLoading.set(true);
    this.voiceApi.listVoices(engine, ttsProvider).subscribe({
      next: (voices) => {
        this.voicesLoading.set(false);
        this.voices.set(voices);
        const current = this.editForm.controls.voice.value;
        if (!voices.some((voice) => voice.id === current)) {
          this.editForm.controls.voice.setValue(voices[0]?.id ?? '');
        }
      },
      error: () => this.voicesLoading.set(false)
    });
  }

  onProviderChange(): void {
    this.editForm.controls.engine.setValue(this.editForm.controls.ttsProvider.value);
    this.loadVoices();
  }

  selectAudiobook(item: AudiobookSummary): void {
    this.selected.set(item);
    this.transcript.set(null);
    this.transcriptError.set(null);
    this.review.set({ segments: {} });
    this.cuts.set([]);
    this.detectTask.set(null);
    this.showOnlyFlagged.set(false);
    this.resegmentMessage.set(null);
    this.resegmentError.set(null);
    this.edits.set({});
    this.openEditors.set(new Set());
    this.editedText.set({});
    this.cutRanges.set({});
    this.stagingIndex.set(null);
    this.stageTask.set(null);
    this.stageError.set(null);
    this.stagingCutIndex.set(null);
    this.stageCutError.set(null);
    this.applyTask.set(null);
    this.applyError.set(null);

    this.api.getTranscript(item.path).subscribe({
      next: (transcript) => this.transcript.set(transcript),
      error: (err) => this.transcriptError.set(_errorMessage(err))
    });
    this.api.getReview(item.path).subscribe({ next: (review) => this.review.set(review) });
    // Cuts from the last completed scan, if any - persisted server-side so
    // they don't disappear on reselect/reload and force a full rescan.
    this.api.getArtifacts(item.path).subscribe({ next: (cuts) => this.cuts.set(cuts) });
    this.api.getEdits(item.path).subscribe({ next: (edits) => this.edits.set(edits) });
  }

  // Segments play one at a time, decoded on demand server-side (see
  // getClipUrl) rather than loading the whole (potentially multi-hour)
  // audiobook into the player up front.
  playSegment(segment: TranscriptSegment): void {
    this._playClip(segment.start_seconds, segment.end_seconds);
  }

  // A merged narration segment can run up to 20+ minutes; playing the whole
  // thing to check on a few seconds of flagged noise isn't practical. This
  // jumps straight to just the flagged span, padded for context.
  playFlaggedCut(cut: ArtifactCut): void {
    this._playClip(
      Math.max(0, cut.start_seconds - _FLAGGED_CLIP_PADDING_SECONDS),
      cut.end_seconds + _FLAGGED_CLIP_PADDING_SECONDS
    );
  }

  flaggedCutsFor(segment: TranscriptSegment): ArtifactCut[] {
    return this.cuts().filter(
      (cut) => segment.start_seconds < cut.end_seconds && segment.end_seconds > cut.start_seconds
    );
  }

  editFor(index: number): PendingEdits[string] | undefined {
    return this.edits()[String(index)];
  }

  isEditorOpen(index: number): boolean {
    return this.openEditors().has(index);
  }

  toggleEditor(index: number): void {
    const next = new Set(this.openEditors());
    if (next.has(index)) {
      next.delete(index);
    } else {
      next.add(index);
    }
    this.openEditors.set(next);
  }

  textFor(index: number, original: string): string {
    if (this.editedText()[index] !== undefined) {
      return this.editedText()[index];
    }
    const edit = this.editFor(index);
    return edit?.kind === 'regenerate' ? edit.text : original;
  }

  onEditText(index: number, value: string): void {
    this.editedText.update((current) => ({ ...current, [index]: value }));
  }

  isStaging(index: number): boolean {
    return this.stagingIndex() === index;
  }

  // Synthesizes the actual replacement audio and saves it server-side -
  // there's no separate throwaway "preview" step, since this *is* the take
  // that gets baked in if the edit is kept. The user listens to it (see
  // playStagedRegeneration) before deciding whether to leave it staged,
  // re-stage with different wording, or discard it.
  stageRegeneration(index: number, originalText: string): void {
    const item = this.selected();
    if (!item) {
      return;
    }
    const { ttsProvider, engine, voice, dialogueVoice, pronunciations, addPauses } =
      this.editForm.getRawValue();

    this.stageError.set(null);
    this.stageTask.set(null);
    this.stagingIndex.set(index);

    this.api
      .stageRegeneration({
        path: item.path,
        segment_index: index,
        text: this.textFor(index, originalText),
        tts_provider: ttsProvider,
        engine,
        voice,
        dialogue_voice: dialogueVoice || null,
        pronunciations: pronunciations || null,
        add_pauses: addPauses
      })
      .subscribe({
        next: ({ task_id }) => {
          this.voiceApi
            .pollTaskUntilDone<{ segment_index: number; edits: PendingEdits }>(task_id)
            .subscribe({
              next: (state) => {
                this.stageTask.set(state);
                if (state.status === 'completed') {
                  this.stagingIndex.set(null);
                  if (state.result) {
                    this.edits.set(state.result.edits);
                  }
                  this.playStagedRegeneration(index);
                } else if (state.status === 'failed') {
                  this.stagingIndex.set(null);
                  this.stageError.set(state.error ?? 'Regeneration failed.');
                }
              },
              error: (err) => {
                this.stagingIndex.set(null);
                this.stageError.set(_errorMessage(err));
              }
            });
        },
        error: (err) => {
          this.stagingIndex.set(null);
          this.stageError.set(_errorMessage(err));
        }
      });
  }

  // The staged take is real audio already saved server-side, so it can be
  // played directly by URL - no task/blob fetch needed.
  playStagedRegeneration(index: number): void {
    const item = this.selected();
    const player = this.playerRef?.nativeElement;
    if (!item || !player) {
      return;
    }
    player.src = this.api.getEditAudioUrl(item.path, index);
    player.load();
    player.play();
  }

  // Defaults to a staged cut's own range, then the segment's own flagged
  // artifact span (if any), then its full bounds - either way the user can
  // still adjust the numbers before staging. A flagged artifact can span a
  // segment boundary (the noise detector works on the raw audio, with no
  // notion of where a segment ends) - clamped to this segment's own span,
  // since a cut can only ever apply within one segment's own audio; the
  // rest of a boundary-crossing artifact still shows up as flagged on the
  // neighboring segment, cut separately there.
  cutRangeFor(index: number, segment: TranscriptSegment): { start: number; end: number } {
    const staged = this.cutRanges()[index];
    if (staged) {
      return staged;
    }
    const edit = this.editFor(index);
    if (edit?.kind === 'cut') {
      return { start: edit.cut_start_seconds, end: edit.cut_end_seconds };
    }
    const flagged = this.flaggedCutsFor(segment)[0];
    return flagged ? _clampToSegment(flagged, segment) : { start: segment.start_seconds, end: segment.end_seconds };
  }

  useFlaggedCutRange(index: number, segment: TranscriptSegment, cut: ArtifactCut): void {
    this.cutRanges.update((current) => ({
      ...current,
      [index]: _clampToSegment(cut, segment)
    }));
  }

  // Whether a flagged artifact reaches past this segment's own bounds -
  // used to warn the user that staging this cut will only remove the part
  // of the noise that falls inside this segment.
  flaggedExceedsSegment(cut: ArtifactCut, segment: TranscriptSegment): boolean {
    return cut.start_seconds < segment.start_seconds || cut.end_seconds > segment.end_seconds;
  }

  setCutRangeStart(index: number, segment: TranscriptSegment, value: number): void {
    const current = this.cutRangeFor(index, segment);
    this.cutRanges.update((ranges) => ({ ...ranges, [index]: { ...current, start: value } }));
  }

  setCutRangeEnd(index: number, segment: TranscriptSegment, value: number): void {
    const current = this.cutRangeFor(index, segment);
    this.cutRanges.update((ranges) => ({ ...ranges, [index]: { ...current, end: value } }));
  }

  previewCutRange(index: number, segment: TranscriptSegment): void {
    const { start, end } = this.cutRangeFor(index, segment);
    this._playClip(start, end);
  }

  cutRangeValid(index: number, segment: TranscriptSegment): boolean {
    const { start, end } = this.cutRangeFor(index, segment);
    return start >= segment.start_seconds && end <= segment.end_seconds && start < end;
  }

  isStagingCut(index: number): boolean {
    return this.stagingCutIndex() === index;
  }

  // Just a manifest write server-side - no ffmpeg work happens until
  // Apply runs - so this is a plain request, not a task to poll.
  stageCut(index: number, segment: TranscriptSegment): void {
    const item = this.selected();
    if (!item || !this.cutRangeValid(index, segment)) {
      return;
    }
    const { start, end } = this.cutRangeFor(index, segment);

    this.stageCutError.set(null);
    this.stagingCutIndex.set(index);
    this.api
      .stageCut({
        path: item.path,
        segment_index: index,
        cut_start_seconds: start,
        cut_end_seconds: end
      })
      .subscribe({
        next: (edits) => {
          this.stagingCutIndex.set(null);
          this.edits.set(edits);
        },
        error: (err) => {
          this.stagingCutIndex.set(null);
          this.stageCutError.set(_errorMessage(err));
        }
      });
  }

  discardEdit(index: number): void {
    const item = this.selected();
    if (!item) {
      return;
    }
    this.api.discardEdit(item.path, index).subscribe({ next: (edits) => this.edits.set(edits) });
  }

  pendingEditCount(): number {
    return Object.keys(this.edits()).length;
  }

  isApplying(): boolean {
    const status = this.applyTask()?.status;
    return status === 'pending' || status === 'running';
  }

  cancelApply(): void {
    const taskId = this.applyTaskId();
    if (taskId) {
      this.voiceApi.cancelTask(taskId).subscribe();
    }
  }

  // Bakes every staged edit into the real audiobook file in one pass - see
  // audit_service.apply_pending_edits. Segment indices don't shift (edits
  // only change what's inside a segment's own span, never add/remove
  // segments), so review state stays valid; only the edits themselves and
  // the artifact scan (timestamps moved) need clearing, both server-side.
  runApply(): void {
    const item = this.selected();
    if (!item || this.pendingEditCount() === 0) {
      return;
    }
    this.applyError.set(null);
    this.applyTask.set(null);

    this.api.applyEdits(item.path).subscribe({
      next: ({ task_id }) => {
        this.applyTaskId.set(task_id);
        this.voiceApi
          .pollTaskUntilDone<{ destination: string; segments_applied: number }>(task_id)
          .subscribe({
            next: (state) => {
              this.applyTask.set(state);
              if (state.status === 'completed') {
                this.openEditors.set(new Set());
                this.editedText.set({});
                this.cutRanges.set({});
                this.edits.set({});
                this.cuts.set([]);
                this.detectTask.set(null);
                this.api.getTranscript(item.path).subscribe({
                  next: (transcript) => this.transcript.set(transcript)
                });
                this.api.getReview(item.path).subscribe({
                  next: (review) => this.review.set(review)
                });
              } else if (state.status === 'failed') {
                this.applyError.set(state.error ?? 'Apply failed.');
              }
            },
            error: (err) => this.applyError.set(_errorMessage(err))
          });
      },
      error: (err) => this.applyError.set(_errorMessage(err))
    });
  }

  private _playClip(startSeconds: number, endSeconds: number): void {
    const item = this.selected();
    const player = this.playerRef?.nativeElement;
    if (!item || !player) {
      return;
    }
    player.src = this.api.getClipUrl(item.path, startSeconds, endSeconds);
    player.load();
    player.play();
  }

  isDetecting(): boolean {
    const status = this.detectTask()?.status;
    return status === 'pending' || status === 'running';
  }

  runDetection(): void {
    const item = this.selected();
    if (!item) {
      return;
    }
    this.detectTask.set(null);
    this.cuts.set([]);
    this.api.detectArtifacts(item.path).subscribe({
      next: ({ task_id }) => {
        this.detectTaskId.set(task_id);
        this.voiceApi.pollTaskUntilDone<{ cuts: ArtifactCut[] }>(task_id).subscribe({
          next: (state) => {
            this.detectTask.set(state);
            if (state.status === 'completed' && state.result) {
              this.cuts.set(state.result.cuts);
            }
          }
        });
      }
    });
  }

  cancelDetection(): void {
    const taskId = this.detectTaskId();
    if (taskId) {
      this.voiceApi.cancelTask(taskId).subscribe();
    }
  }

  // Splitting is fast (in-memory text processing plus one JSON write, no
  // TTS involved), so unlike detection this is a plain request rather than
  // a task the user has to poll or cancel.
  runResegment(): void {
    const item = this.selected();
    if (!item) {
      return;
    }
    this.resegmenting.set(true);
    this.resegmentMessage.set(null);
    this.resegmentError.set(null);
    this.api.resegmentTranscript(item.path).subscribe({
      next: (result) => {
        this.resegmenting.set(false);
        const pieceCount =
          result.new_segment_count - result.original_segment_count + result.segments_split;
        this.resegmentMessage.set(`Split ${result.segments_split} segment(s) into ${pieceCount} pieces.`);
        // Segment indices shifted for everything after a split, and review
        // state (keyed by index) was cleared server-side to match - reload
        // both rather than trying to patch them in place. Any staged edits
        // would be just as stale (same indexing problem), so drop those too.
        this.cuts.set([]);
        this.edits.set({});
        this.openEditors.set(new Set());
        this.editedText.set({});
        this.cutRanges.set({});
        this.api.getTranscript(item.path).subscribe({
          next: (transcript) => this.transcript.set(transcript)
        });
        this.api.getReview(item.path).subscribe({ next: (review) => this.review.set(review) });
        this.api.getArtifacts(item.path).subscribe({ next: (cuts) => this.cuts.set(cuts) });
      },
      error: (err) => {
        this.resegmenting.set(false);
        this.resegmentError.set(_errorMessage(err));
      }
    });
  }

  isNewChapter(index: number): boolean {
    const segments = this.transcript()?.segments ?? [];
    return index === 0 || segments[index]?.chapter_title !== segments[index - 1]?.chapter_title;
  }

  isFlagged(segment: TranscriptSegment): boolean {
    return this.flaggedCutsFor(segment).length > 0;
  }

  toggleShowOnlyFlagged(): void {
    this.showOnlyFlagged.update((current) => !current);
  }

  // Segments keep their real index (needed for review/edit state, which is
  // keyed by position in the full transcript) even when the flagged-only
  // filter hides most of the list.
  visibleSegments(): { segment: TranscriptSegment; index: number }[] {
    const segments = this.transcript()?.segments ?? [];
    const onlyFlagged = this.showOnlyFlagged();
    return segments
      .map((segment, index) => ({ segment, index }))
      .filter(({ segment }) => !onlyFlagged || this.isFlagged(segment));
  }

  reviewStatus(index: number): ReviewStatus | 'unreviewed' {
    return this.review().segments[String(index)]?.status ?? 'unreviewed';
  }

  setReview(index: number, status: ReviewStatus): void {
    const item = this.selected();
    if (!item) {
      return;
    }
    this.api
      .setReviewStatus(item.path, index, status)
      .subscribe({ next: (review) => this.review.set(review) });
  }
}

function _clampToSegment(
  cut: ArtifactCut,
  segment: TranscriptSegment
): { start: number; end: number } {
  return {
    start: Math.max(cut.start_seconds, segment.start_seconds),
    end: Math.min(cut.end_seconds, segment.end_seconds)
  };
}

function _errorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'error' in err) {
    const body = (err as { error?: unknown }).error;
    if (body && typeof body === 'object' && 'error' in body) {
      return String((body as { error?: unknown }).error);
    }
  }
  return 'Request failed. Is the API server running?';
}
