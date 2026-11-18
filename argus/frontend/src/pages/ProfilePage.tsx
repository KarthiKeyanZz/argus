import { Download, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { useDeleteAllData } from "@/api/queries";
import { Input } from "@/components/ui/form";
import { Button, Card, PageHeader } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { BasicsCard, EducationCard, ExperienceCard, ProjectsCard, SkillsCard } from "@/pages/profile/ProfileSections";
import { ResumeImport } from "@/pages/profile/ResumeImport";

function DataCard() {
  const remove = useDeleteAllData();
  const toast = useToast();
  const [confirm, setConfirm] = useState("");

  const exportData = async () => {
    const response = await fetch("/api/v1/profile/export");
    const blob = new Blob([JSON.stringify(await response.json(), null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `argus-export-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <Card title="Your data" description="Everything stays in your local PostgreSQL. Export it, or delete it permanently.">
      <div className="flex flex-wrap items-center gap-3">
        <Button icon={<Download className="size-4" />} onClick={() => void exportData()}>Export JSON</Button>
        <div className="flex items-center gap-2">
          <Input className="w-40" placeholder='Type "DELETE"' value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <Button
            variant="danger"
            className="whitespace-nowrap"
            icon={<ShieldAlert className="size-4" />}
            disabled={confirm !== "DELETE"}
            loading={remove.isPending}
            onClick={() => remove.mutate(undefined, { onSuccess: () => { toast.success("All personal data deleted"); setConfirm(""); }, onError: toast.error })}
          >
            Delete all personal data
          </Button>
        </div>
      </div>
    </Card>
  );
}

export function ProfilePage() {
  return (
    <>
      <PageHeader title="Profile" description="Your verified career facts. ARGUS never invents anything that isn't here." />
      <div className="space-y-6">
        <ResumeImport />
        <div className="grid gap-6 lg:grid-cols-2">
          <BasicsCard />
          <SkillsCard />
        </div>
        <ExperienceCard />
        <div className="grid gap-6 lg:grid-cols-2">
          <EducationCard />
          <ProjectsCard />
        </div>
        <DataCard />
      </div>
    </>
  );
}
