import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { BOOK_SOURCES, DEFAULT_EBOOKS_FOLDER } from '../../core/constants';
import { EbookExportApiService } from '../../core/ebook-export-api.service';
import { ExportEbookResult, ExtractedTextSummary } from '../../core/models';
import { TextExtractionApiService } from '../../core/text-extraction-api.service';
import { DEFAULT_EXTRACTED_TEXTS_FOLDER } from '../../core/constants';
import { FilePickerComponent } from '../../shared/file-picker/file-picker.component';

@Component({
  selector: 'app-ebooks',
  standalone: true,
  imports: [ReactiveFormsModule, FilePickerComponent],
  templateUrl: './ebooks.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './ebooks.component.css'
})
export class EbooksComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly api = inject(EbookExportApiService);
  private readonly textApi = inject(TextExtractionApiService);

  readonly sources = BOOK_SOURCES;

  readonly form = this.formBuilder.nonNullable.group({
    source: ['ao3', Validators.required],
    identifier: ['', Validators.required],
    format: ['epub', Validators.required],
    target: [DEFAULT_EBOOKS_FOLDER, Validators.required]
  });

  readonly formats = signal<string[]>(['epub']);
  readonly savedTexts = signal<ExtractedTextSummary[]>([]);

  readonly running = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<ExportEbookResult | null>(null);

  ngOnInit(): void {
    this.api.formats().subscribe({
      next: (response) => {
        this.formats.set(response.formats);
        if (this.form.controls.target.value === DEFAULT_EBOOKS_FOLDER) {
          this.form.controls.target.setValue(response.default_folder);
        }
      },
      error: (err) => this.error.set(_errorMessage(err))
    });
    this.textApi.listExtractedTexts(DEFAULT_EXTRACTED_TEXTS_FOLDER).subscribe({
      next: (texts) => this.savedTexts.set(texts),
      error: () => this.savedTexts.set([])
    });
  }

  source(): string {
    return this.form.controls.source.value;
  }

  identifierPlaceholder(): string {
    return this.sources.find((option) => option.value === this.source())?.identifierPlaceholder ?? '';
  }

  onSourceChange(): void {
    this.form.controls.identifier.setValue('');
    this.result.set(null);
  }

  onPathPicked(path: string): void {
    this.form.controls.identifier.setValue(path);
  }

  onTargetPicked(path: string): void {
    this.form.controls.target.setValue(path);
  }

  isSeries(): boolean {
    const identifier = this.form.controls.identifier.value;
    return this.source() === 'ao3' && /series/i.test(identifier);
  }

  create(): void {
    if (this.form.invalid || this.running()) {
      return;
    }
    const { identifier, target, source, format } = this.form.getRawValue();
    this.running.set(true);
    this.error.set(null);
    this.result.set(null);

    this.api.exportEbook(identifier.trim(), target.trim(), source, format).subscribe({
      next: (result) => {
        this.running.set(false);
        this.result.set(result);
      },
      error: (err) => {
        this.running.set(false);
        this.error.set(_errorMessage(err));
      }
    });
  }
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
