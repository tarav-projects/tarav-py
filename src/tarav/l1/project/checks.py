"""The Project's check composition and execution integration."""

from tarav.l1.checks import CheckProvider, CheckSuite


# tarav.breadcrumb 96999528b4c0
class ChecksManager(CheckProvider.Checks):
    """Build and run this Project's checks; action updates are a separate integration."""

    def suite(self) -> CheckSuite:
        from tarav.l1.git.hooks import git_hooks_suite
        from .files import ProjectFilesCheck

        return CheckSuite([ProjectFilesCheck(self.obj),
                           self.obj.agents.agents_md.checks.suite(),
                           self.obj.agents.skills.checks.suite(),
                           git_hooks_suite(self.obj)],
                          name=self.obj.name, repositories=self.obj.repositories())

    def own(self) -> CheckSuite:
        """Checks of this Project alone, without its member Projects."""
        return self.suite()


__all__ = ["ChecksManager"]
