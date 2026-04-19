import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  /** If set, back navigates here; otherwise uses browser history, then falls back to `/` */
  backTo?: string;
  className?: string;
};

/**
 * Consistent page title row with an optional back control so nested views are not stuck behind the sidebar only.
 */
export function PageHeader({ title, subtitle, backTo, className = '' }: PageHeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const handleBack = () => {
    if (backTo) {
      navigate(backTo);
      return;
    }
    if (location.key !== 'default') {
      navigate(-1);
      return;
    }
    navigate('/');
  };

  return (
    <div className={`flex flex-col gap-1 mb-6 ${className}`}>
      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="shrink-0 h-9 w-9"
          onClick={handleBack}
          aria-label="Go back"
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight truncate">{title}</h1>
          {subtitle ? <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p> : null}
        </div>
      </div>
    </div>
  );
}

export default PageHeader;
