import client from './client'

export interface ResumeUploadResponse {
  review_id: string
  status: string
  message: string
}

export interface DimensionScore {
  key: string
  dimension: string
  score: number
  weight: number
  issues: string[]
  suggestions: string[]
}

export interface IssueItem {
  priority: 'high' | 'medium' | 'low'
  dimension: string
  description: string
  location: string
  suggestion: string
}

export interface ResumeSummary {
  highlights: string[]
  core_improvements: string[]
  overall_comment: string
  fit_assessment: string
}

export interface ReviewDetail {
  review_id: string
  status: 'processing' | 'done' | 'failed'
  error_msg?: string
  target_position?: string
  job_description?: string
  weighted_score?: number
  dimension_scores?: DimensionScore[]
  issues?: IssueItem[]
  summary?: ResumeSummary
}

export interface ReviewListItem {
  review_id: string
  status: string
  target_position?: string
  created_at: string
  weighted_score?: number
}

export const resumeApi = {
  upload: (
    file: File,
    data: { target_position: string; job_description: string },
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('target_position', data.target_position)
    form.append('job_description', data.job_description)
    return client.post<ResumeUploadResponse>('/resume/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  getReview: (reviewId: string) =>
    client.get<ReviewDetail>(`/resume/reviews/${reviewId}`),

  listReviews: () =>
    client.get<{ items: ReviewListItem[]; total: number }>('/resume/reviews'),

  deleteReview: (reviewId: string) =>
    client.delete(`/resume/reviews/${reviewId}`),
}
