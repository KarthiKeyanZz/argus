/**
 * React Query hooks: one place for every server interaction.
 * Query keys are hierarchical so related views refresh together after a mutation.
 */
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api, unwrap, uploadResume, type Schemas } from "./client";

export const keys = {
  health: ["health"] as const,
  system: ["system"] as const,
  jobs: (filters: object) => ["jobs", "list", filters] as const,
  job: (id: number) => ["jobs", "detail", id] as const,
  shortlist: (includeFailed: boolean) => ["jobs", "shortlist", includeFailed] as const,
  profile: ["profile"] as const,
  skills: ["profile", "skills"] as const,
  section: (name: SectionName) => ["profile", "section", name] as const,
  resumes: ["resumes"] as const,
  preferences: ["preferences"] as const,
  companies: (filters: object) => ["companies", filters] as const,
  tasks: (status: string | undefined) => ["tasks", status ?? "all"] as const,
  task: (id: number) => ["tasks", "one", id] as const,
  audit: ["audit"] as const,
  models: ["llm", "models"] as const,
};

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

// ----------------------------------------------------------------------------- system

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: async () => {
      const r = await api.GET("/api/v1/health/ready");
      return (r.data ?? r.error) as Schemas["Readiness"]; // 503 still carries the body
    },
    refetchInterval: 15_000,
  });
}

export function useSystemState() {
  return useQuery({
    queryKey: keys.system,
    queryFn: () => unwrap(api.GET("/api/v1/system/state")),
    refetchInterval: 10_000,
  });
}

export function useSetPaused() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (paused: boolean) =>
      paused
        ? unwrap(api.POST("/api/v1/system/pause", { body: { reason: "Paused from the dashboard" } }))
        : unwrap(api.POST("/api/v1/system/resume")),
    onSuccess: (state) => qc.setQueryData(keys.system, state),
  });
}

// ----------------------------------------------------------------------------- tasks

/** Poll a background task until it finishes; then run `onDone`. */
export function useTask(id: number | null, onDone?: (task: Schemas["TaskOut"]) => void) {
  return useQuery({
    queryKey: keys.task(id ?? 0),
    enabled: id !== null,
    queryFn: async () => {
      const task = await unwrap(api.GET("/api/v1/tasks/{task_id}", { params: { path: { task_id: id! } } }));
      if (TERMINAL.has(task.status)) onDone?.(task);
      return task;
    },
    refetchInterval: (q) => (q.state.data && TERMINAL.has(q.state.data.status) ? false : 1000),
  });
}

export function useTasks(status?: Schemas["TaskOut"]["status"]) {
  return useQuery({
    queryKey: keys.tasks(status),
    queryFn: () => unwrap(api.GET("/api/v1/tasks", { params: { query: { status, limit: 50 } } })),
    refetchInterval: 3000,
  });
}

export function useEnqueueTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kind: Schemas["TaskCreate"]["kind"]) => unwrap(api.POST("/api/v1/tasks", { body: { kind } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useAuditEvents() {
  return useInfiniteQuery({
    queryKey: keys.audit,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/audit-events", { params: { query: { limit: 50, cursor: pageParam } } })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

// ----------------------------------------------------------------------------- jobs

export interface JobFilters {
  q?: string;
  status?: Schemas["JobSummary"]["status"];
  work_mode?: Schemas["JobSummary"]["work_mode"];
}

export function useJobs(filters: JobFilters) {
  return useInfiniteQuery({
    queryKey: keys.jobs(filters),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/jobs", {
          params: { query: { ...filters, q: filters.q || undefined, limit: 25, cursor: pageParam } },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}

export function useShortlist(includeFailed: boolean) {
  return useInfiniteQuery({
    queryKey: keys.shortlist(includeFailed),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/matching/shortlist", {
          params: { query: { include_failed: includeFailed, limit: 25, cursor: pageParam } },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useJob(id: number) {
  return useQuery({
    queryKey: keys.job(id),
    queryFn: () => unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } })),
  });
}

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["ManualJobCreate"]) => unwrap(api.POST("/api/v1/jobs", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useJobAction(kind: "extract" | "match") {
  return useMutation({
    mutationFn: (jobId: number) =>
      kind === "extract"
        ? unwrap(api.POST("/api/v1/jobs/{job_id}/extract", { params: { path: { job_id: jobId } } }))
        : unwrap(api.POST("/api/v1/jobs/{job_id}/match", { params: { path: { job_id: jobId } } })),
  });
}

export function useRunMatching() {
  return useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/matching/run")) });
}

// ----------------------------------------------------------------------------- profile

export function useProfile() {
  return useQuery({ queryKey: keys.profile, queryFn: () => unwrap(api.GET("/api/v1/profile")) });
}

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["ProfileUpdate"]) => unwrap(api.PUT("/api/v1/profile", { body })),
    onSuccess: (data) => qc.setQueryData(keys.profile, data),
  });
}

export function useSkills() {
  return useQuery({ queryKey: keys.skills, queryFn: () => unwrap(api.GET("/api/v1/profile/skills")) });
}

export function useSkillMutations() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: keys.skills });
  return {
    add: useMutation({
      mutationFn: (name: string) => unwrap(api.POST("/api/v1/profile/skills", { body: { name, verified: true } })),
      onSuccess: refresh,
    }),
    verify: useMutation({
      mutationFn: ({ id, verified }: { id: number; verified: boolean }) =>
        unwrap(
          api.PATCH("/api/v1/profile/skills/{skill_id}", { params: { path: { skill_id: id } }, body: { verified } }),
        ),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) =>
        unwrap(api.DELETE("/api/v1/profile/skills/{skill_id}", { params: { path: { skill_id: id } } })),
      onSuccess: refresh,
    }),
  };
}

export type SectionName = "experience" | "education" | "projects";

export function useExperience() {
  return useQuery({
    queryKey: keys.section("experience"),
    queryFn: () => unwrap(api.GET("/api/v1/profile/experience")),
  });
}

export function useEducation() {
  return useQuery({
    queryKey: keys.section("education"),
    queryFn: () => unwrap(api.GET("/api/v1/profile/education")),
  });
}

export function useProjects() {
  return useQuery({
    queryKey: keys.section("projects"),
    queryFn: () => unwrap(api.GET("/api/v1/profile/projects")),
  });
}

export function useSectionMutations() {
  const qc = useQueryClient();
  const refresh = (name: SectionName) => qc.invalidateQueries({ queryKey: keys.section(name) });
  return {
    addExperience: useMutation({
      mutationFn: (body: Schemas["ExperienceIn"]) => unwrap(api.POST("/api/v1/profile/experience", { body })),
      onSuccess: () => refresh("experience"),
    }),
    addEducation: useMutation({
      mutationFn: (body: Schemas["EducationIn"]) => unwrap(api.POST("/api/v1/profile/education", { body })),
      onSuccess: () => refresh("education"),
    }),
    addProject: useMutation({
      mutationFn: (body: Schemas["ProjectIn"]) => unwrap(api.POST("/api/v1/profile/projects", { body })),
      onSuccess: () => refresh("projects"),
    }),
    remove: useMutation({
      mutationFn: async ({ section, id }: { section: SectionName; id: number }) => {
        const params = { params: { path: { row_id: id } } };
        if (section === "experience") return unwrap(api.DELETE("/api/v1/profile/experience/{row_id}", params));
        if (section === "education") return unwrap(api.DELETE("/api/v1/profile/education/{row_id}", params));
        return unwrap(api.DELETE("/api/v1/profile/projects/{row_id}", params));
      },
      onSuccess: (_d, v) => refresh(v.section),
    }),
  };
}

export function useDeleteAllData() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/profile/data", { params: { query: { confirm: "DELETE" } } })),
    onSuccess: () => qc.invalidateQueries(),
  });
}

// ----------------------------------------------------------------------------- resume

export function useResumes() {
  return useQuery({ queryKey: keys.resumes, queryFn: () => unwrap(api.GET("/api/v1/resumes")) });
}

export function useResumeMutations() {
  const qc = useQueryClient();
  return {
    upload: useMutation({
      mutationFn: (file: File) => uploadResume(file),
      onSuccess: () => qc.invalidateQueries({ queryKey: keys.resumes }),
    }),
    parse: useMutation({
      mutationFn: (id: number) =>
        unwrap(api.POST("/api/v1/resumes/{resume_id}/parse", { params: { path: { resume_id: id } } })),
    }),
    importFacts: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Schemas["ResumeImportRequest"] }) =>
        unwrap(api.POST("/api/v1/resumes/{resume_id}/import", { params: { path: { resume_id: id } }, body })),
      onSuccess: () => qc.invalidateQueries({ queryKey: ["profile"] }),
    }),
    remove: useMutation({
      mutationFn: (id: number) =>
        unwrap(api.DELETE("/api/v1/resumes/{resume_id}", { params: { path: { resume_id: id } } })),
      onSuccess: () => qc.invalidateQueries({ queryKey: keys.resumes }),
    }),
  };
}

// ----------------------------------------------------------------------------- preferences

export function usePreferences() {
  return useQuery({ queryKey: keys.preferences, queryFn: () => unwrap(api.GET("/api/v1/preferences")) });
}

export function useSavePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["PreferencesUpdate"]) => unwrap(api.PUT("/api/v1/preferences", { body })),
    onSuccess: (data) => qc.setQueryData(keys.preferences, data),
  });
}

// ----------------------------------------------------------------------------- companies

export function useCompanies(q: string) {
  return useInfiniteQuery({
    queryKey: keys.companies({ q }),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/companies", { params: { query: { q: q || undefined, limit: 50, cursor: pageParam } } })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}

export function useCompanyMutations() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["companies"] });
  return {
    create: useMutation({
      mutationFn: (body: Schemas["CompanyCreate"]) => unwrap(api.POST("/api/v1/companies", { body })),
      onSuccess: refresh,
    }),
    toggle: useMutation({
      mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
        unwrap(api.PATCH("/api/v1/companies/{company_id}", { params: { path: { company_id: id } }, body: { enabled } })),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) =>
        unwrap(api.DELETE("/api/v1/companies/{company_id}", { params: { path: { company_id: id } } })),
      onSuccess: refresh,
    }),
    detect: useMutation({
      mutationFn: (url: string) => unwrap(api.POST("/api/v1/companies/detect-ats", { body: { url } })),
    }),
  };
}

// ----------------------------------------------------------------------------- llm lab

export function useModels() {
  return useQuery({ queryKey: keys.models, queryFn: () => unwrap(api.GET("/api/v1/llm/models")), refetchInterval: 10_000 });
}

export function useGenerate() {
  return useMutation({
    mutationFn: (body: Schemas["GenerateRequest"]) => unwrap(api.POST("/api/v1/llm/generate", { body })),
  });
}

export function useSimilarity() {
  return useMutation({
    mutationFn: (body: Schemas["SimilarityRequest"]) => unwrap(api.POST("/api/v1/llm/similarity", { body })),
  });
}
