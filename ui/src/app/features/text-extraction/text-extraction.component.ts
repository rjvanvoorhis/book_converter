import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { FilePickerComponent } from '../../shared/file-picker/file-picker.component';
import { TextExtractionApiService } from '../../core/text-extraction-api.service';
import {
  COPY_EDITORS,
  DEFAULT_EXTRACTED_TEXTS_FOLDER,
  EXTRACTABLE_BOOK_SOURCES
} from '../../core/constants';
import {
  ChapterEditDiff,
  ExtractedTextSummary,
  LoadEbookResult,
  TextReviewFlag
} from '../../core/models';

@Component({
  selector: 'app-text-extraction',
  standalone: true,
  imports: [ReactiveFormsModule, FilePickerComponent],
  templateUrl: './text-extraction.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './text-extraction.component.css'
})
export class TextExtractionComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly api = inject(TextExtractionApiService);

  readonly sources = EXTRACTABLE_BOOK_SOURCES;
  readonly copyEditors = COPY_EDITORS;

  readonly loadForm = this.formBuilder.nonNullable.group({
    source: ['file', Validators.required],
    identifier: ['', Validators.required]
  });

  readonly loading = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly loaded = signal<LoadEbookResult | null>(null);

  readonly targetFolder = this.formBuilder.nonNullable.control('', Validators.required);
  readonly saving = signal(false);
  readonly saveError = signal<string | null>(null);
  readonly savedDestination = signal<string | null>(null);

  readonly libraryFolder = this.formBuilder.nonNullable.control(
    DEFAULT_EXTRACTED_TEXTS_FOLDER
  );
  readonly library = signal<ExtractedTextSummary[]>([]);
  readonly libraryLoading = signal(false);
  readonly libraryError = signal<string | null>(null);

  readonly copyeditingPath = signal<string | null>(null);
  readonly copyeditorByPath = signal<Record<string, string>>({});
  readonly copyeditError = signal<string | null>(null);
  readonly copyeditResultByPath = signal<Record<string, ChapterEditDiff[]>>({});

  readonly copiedPath = signal<string | null>(null);

  readonly reviewingItem = signal<ExtractedTextSummary | null>(null);
  readonly reviewFlagDraft = signal<TextReviewFlag | null>(null);
  readonly reviewNoteDraft = this.formBuilder.nonNullable.control('');
  readonly reviewSaving = signal(false);
  readonly reviewError = signal<string | null>(null);

  ngOnInit(): void {
    this.loadLibrary();
  }

  identifierPlaceholder(): string {
    const source = this.loadForm.controls.source.value;
    return this.sources.find((option) => option.value === source)?.identifierPlaceholder ?? '';
  }

  isFileSource(): boolean {
    return this.loadForm.controls.source.value === 'file';
  }

  onFilePicked(path: string): void {
    this.loadForm.controls.identifier.setValue(path);
  }

  loadEbook(): void {
    if (this.loadForm.invalid) {
      return;
    }
    const { identifier, source } = this.loadForm.getRawValue();

    this.loading.set(true);
    this.loadError.set(null);
    this.loaded.set(null);
    this.savedDestination.set(null);
    this.saveError.set(null);

    this.api.loadEbook(identifier, source).subscribe({
      next: (result) => {
        this.loading.set(false);
        this.loaded.set(result);
        this.targetFolder.setValue(
          `${DEFAULT_EXTRACTED_TEXTS_FOLDER}/${_slugify(result.title || identifier)}`
        );
      },
      error: (err) => {
        this.loading.set(false);
        this.loadError.set(_errorMessage(err));
      }
    });
  }

  saveForLater(): void {
    const loaded = this.loaded();
    if (!loaded || this.targetFolder.invalid) {
      return;
    }
    const { identifier, source } = this.loadForm.getRawValue();

    this.saving.set(true);
    this.saveError.set(null);
    this.savedDestination.set(null);

    this.api.extractText(identifier, this.targetFolder.value.trim(), source).subscribe({
      next: (result) => {
        this.saving.set(false);
        this.savedDestination.set(result.destination);
        this.loadLibrary();
      },
      error: (err) => {
        this.saving.set(false);
        this.saveError.set(_errorMessage(err));
      }
    });
  }

  loadLibrary(): void {
    const folder = this.libraryFolder.value.trim() || DEFAULT_EXTRACTED_TEXTS_FOLDER;
    this.libraryLoading.set(true);
    this.libraryError.set(null);
    this.api.listExtractedTexts(folder).subscribe({
      next: (texts) => {
        this.libraryLoading.set(false);
        this.library.set(texts);
      },
      error: (err) => {
        this.libraryLoading.set(false);
        this.libraryError.set(_errorMessage(err));
      }
    });
  }

  deleteExtractedText(item: ExtractedTextSummary): void {
    this.api.deleteExtractedText(item.path).subscribe({
      next: () => this.loadLibrary()
    });
  }

  copyPath(path: string): void {
    navigator.clipboard?.writeText(path).then(() => {
      this.copiedPath.set(path);
      setTimeout(() => {
        if (this.copiedPath() === path) {
          this.copiedPath.set(null);
        }
      }, 1500);
    });
  }

  isCopyeditOpen(path: string): boolean {
    return this.copyeditingPath() === path;
  }

  toggleCopyedit(path: string): void {
    this.copyeditingPath.set(this.isCopyeditOpen(path) ? null : path);
    this.copyeditError.set(null);
  }

  editorFor(path: string): string {
    return this.copyeditorByPath()[path] ?? this.copyEditors[0]?.value ?? 'languagetool';
  }

  setEditorFor(path: string, editor: string): void {
    this.copyeditorByPath.update((current) => ({ ...current, [path]: editor }));
  }

  changedChaptersFor(path: string): ChapterEditDiff[] {
    return this.copyeditResultByPath()[path] ?? [];
  }

  private readonly copyeditRunningPath = signal<string | null>(null);

  isCopyediting(path: string): boolean {
    return this.copyeditRunningPath() === path;
  }

  runCopyedit(path: string): void {
    this.copyeditRunningPath.set(path);
    this.copyeditError.set(null);
    this.api.copyedit(path, this.editorFor(path)).subscribe({
      next: (result) => {
        this.copyeditRunningPath.set(null);
        this.copyeditResultByPath.update((current) => ({
          ...current,
          [path]: result.chapters.filter((chapter) => chapter.diff)
        }));
      },
      error: (err) => {
        this.copyeditRunningPath.set(null);
        this.copyeditError.set(_errorMessage(err));
      }
    });
  }

  openReview(item: ExtractedTextSummary): void {
    this.reviewingItem.set(item);
    this.reviewFlagDraft.set(item.review_flag);
    this.reviewNoteDraft.setValue(item.review_note ?? '');
    this.reviewError.set(null);
  }

  closeReview(): void {
    this.reviewingItem.set(null);
    this.reviewSaving.set(false);
  }

  toggleReviewFlag(flag: TextReviewFlag): void {
    this.reviewFlagDraft.update((current) => (current === flag ? null : flag));
  }

  saveReview(): void {
    const item = this.reviewingItem();
    if (!item || this.reviewSaving()) {
      return;
    }
    const note = this.reviewNoteDraft.value.trim() || null;
    const flag = this.reviewFlagDraft();

    this.reviewSaving.set(true);
    this.reviewError.set(null);
    this.api.saveTextReview(item.path, flag, note).subscribe({
      next: (result) => {
        this.reviewSaving.set(false);
        this.library.update((items) =>
          items.map((existing) =>
            existing.path === result.path
              ? { ...existing, review_flag: result.flag, review_note: result.note }
              : existing
          )
        );
        this.closeReview();
      },
      error: (err) => {
        this.reviewSaving.set(false);
        this.reviewError.set(_errorMessage(err));
      }
    });
  }
}

function _slugify(title: string): string {
  const slug = title
    .trim()
    .toLowerCase()
    .replace(/[^\w]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'book';
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
