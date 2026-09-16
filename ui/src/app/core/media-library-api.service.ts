import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  GroupStatusResult,
  HealthCheckLibraryResult,
  HealthCheckResult,
  ImportWorkRequest,
  ImportWorkResult,
  MediaLibraryItem,
  MediaLibrarySummary,
  SyncSeriesResult
} from './models';

@Injectable({ providedIn: 'root' })
export class MediaLibraryApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  listLibraries(): Observable<MediaLibrarySummary[]> {
    return this.http
      .get<{ libraries: MediaLibrarySummary[] }>(`${this.baseUrl}/media-library/libraries`)
      .pipe(map((response) => response.libraries));
  }

  listItems(libraryId: string): Observable<MediaLibraryItem[]> {
    return this.http
      .get<{ items: MediaLibraryItem[] }>(
        `${this.baseUrl}/media-library/libraries/${encodeURIComponent(libraryId)}/items`
      )
      .pipe(map((response) => response.items));
  }

  /** Always performs the copy + metadata.json write + scan, even if the
   * work already appears to be there - Audiobookshelf is the only source of
   * truth for import status (see groupStatus), so there's no local
   * idempotency to skip. */
  importWork(request: ImportWorkRequest): Observable<ImportWorkResult> {
    return this.http.post<ImportWorkResult>(`${this.baseUrl}/media-library/import`, request);
  }

  /** Whether a library folder is reachable/writable right now, without
   * changing anything - see registerFolder to actually bootstrap it. */
  healthCheckFolder(libraryId: string, folderId: string): Observable<HealthCheckResult> {
    return this.http.get<HealthCheckResult>(
      `${this.baseUrl}/media-library/libraries/${encodeURIComponent(libraryId)}/folders/${encodeURIComponent(folderId)}/health`
    );
  }

  /** Checks every folder in a library at once, so a library picker can show
   * accessibility for the whole library up front. */
  healthCheckLibrary(libraryId: string): Observable<HealthCheckLibraryResult> {
    return this.http.get<HealthCheckLibraryResult>(
      `${this.baseUrl}/media-library/libraries/${encodeURIComponent(libraryId)}/health`
    );
  }

  /** Sets up whatever the folder needs to become usable (e.g. mounting a
   * configured NAS share) - safe to call even if it's already healthy. */
  registerFolder(libraryId: string, folderId: string): Observable<HealthCheckResult> {
    return this.http.post<HealthCheckResult>(
      `${this.baseUrl}/media-library/libraries/${encodeURIComponent(libraryId)}/folders/${encodeURIComponent(folderId)}/register`,
      {}
    );
  }

  /** Audiobookshelf Series in a library with no matching local group yet -
   * a discovery aid, not an importer (a group's members are assigned
   * locally before anything is imported - see organization-api.service). */
  unlinkedSeries(libraryId: string): Observable<string[]> {
    return this.http
      .get<SyncSeriesResult>(
        `${this.baseUrl}/media-library/libraries/${encodeURIComponent(libraryId)}/unlinked-series`
      )
      .pipe(map((response) => response.unlinked_series_names));
  }

  /** Whether each of a group's members is actually present in its bound
   * library right now, checked live against Audiobookshelf every call. */
  groupStatus(groupId: string): Observable<GroupStatusResult> {
    return this.http.get<GroupStatusResult>(
      `${this.baseUrl}/media-library/groups/${encodeURIComponent(groupId)}/status`
    );
  }
}
