import math
from typing import Any, Dict, Optional, Type, List
from molmass import Formula
from bson import ObjectId
from datetime import datetime
from alab_control.labman.error import WorkflowFullError
from enum import Enum, auto


class InputFile:
    MAX_JAR_VOLUME_UL = 22000  # 22 mL

    def __init__(
        self,
        powder_dispenses: Dict[str, float],
        heating_duration_s: Optional[int] = None,
        ethanol_volume_ul: int = 10000,
        transfer_volume_ul: Optional[int] = None,
        mixer_speed_rpm: int = 2000,
        mixer_duration_s: int = 60 * 9,
        min_transfer_mass_g: Optional[int] = None,
        replicates: int = 1,
        allow_replicates: bool = True,
        time_added: datetime = None,
    ):
        """A single InputFile to construct a Labman workflow.

        Args:
            powder_dispenses (Dict[str, float]): Powders and masses to mix into the crucible. Should be of form {"powder_name": mass_g, "powder_name": mass_g, ...}
            heating_duration_s (int, optional): Duration (seconds) to heat the crucible to boil off all ethanol. For reference, the crucible is heated around 80C. Defaults to 60*30.
            ethanol_volume_ul (int, optional): The volume (microliters) of ethanol to mix in each crucible. Too little results in a slurry that cannot be aliquoted from the mixing pot into the crucible. Too much may reduce the degree to which the powders are mixed, and will require a longer heating duration. Defaults to 10000.
            transfer_volume_ul (int, optional): The target volume (microliters) of slurry to transfer from the mixing pot into the crucible. Defaults to 10000.
            mixer_speed_rpm (int, optional): The speed (revolutions per minute) at which to rotate the speedmixer. This step mixes and slightly mills the powders in the mixing pot prior to transfer into the crucible. The speed mixer can spin at up to 2500 rpm. Defaults to 2000.
            mixer_duration_s (int, optional): The duration (seconds) for which to mix the speed mixer. Defaults to 60*9.
            min_transfer_mass_g (int, optional): The minimum mass (g) to transfer from the mixing pot to the crucible. If the mass is below this value (as may be the case with too viscous of a slurry), the workflow will indicate that the crucible has "failed". We can still proceed with the experiment -- this is just a check that sets a flag in the workflow results. Defaults to 5.
            replicates (int, optional): Number of copies of this same inputfile to process. Defaults to 1.
            allow_replicates (bool, optional): Whether to allow this inputfile to be replicated. If False, this inputfile will never be batched (ie always one mixing pot to one crucible). Defaults to True.
            time_added (datetime, optional): Time at which this inputfile was created. This is used by the workflow batching routine to prioritize older inputfiles. Defaults to None, in which case the current time is used.


        """
        if len(powder_dispenses) == 0:
            raise ValueError("`powder_dispenses` must be non-empty!")

        if any([mass <= 0 for powder, mass in powder_dispenses.items()]):
            raise ValueError(
                "Invalid mass provided in `powder_dispenses`. All masses must be >= 0 grams!"
            )
        self.powder_dispenses = powder_dispenses

        if ethanol_volume_ul < 0 or ethanol_volume_ul > self.MAX_JAR_VOLUME_UL:
            raise ValueError(
                "`ethanol_volume_ul` must be between 0 and {self.MAX_JAR_VOLUME_UL} microliters (0 and 35 mL)! "
            )
        self.ethanol_volume = ethanol_volume_ul
        self.transfer_volume = transfer_volume_ul or self.ethanol_volume

        heating_duration_s = heating_duration_s or self.ethanol_volume * (
            90 * 60 / 10000
        )  # 90 minutes per 10 mL of ethanol as a conservative guess
        if heating_duration_s < 0 or heating_duration_s > 240 * 60:
            raise ValueError(
                "`heating_duration_s` must be between 0 and 14400 seconds (0 and 240 minutes)! "
            )
        self.heating_duration = heating_duration_s

        self.mixer_speed = mixer_speed_rpm
        if mixer_duration_s < 0 or mixer_duration_s > 15 * 60:
            raise ValueError(
                "`mixer_duration_s` must be between 0 and 900 seconds (0 and 15 minutes)! "
            )
        self.mixer_duration = mixer_duration_s
        if min_transfer_mass_g is not None:
            self.min_transfer_mass = min_transfer_mass_g
        else:
            """
            We can estimate the mass we expect to collect if things go well.

            We know the mass is at least the mass of the transfer volume of ethanol (etOH density = 0.789 g/cm^3)
            We also know that, ideally, we collect all of the mass of powders we dispense.

            Finally, we know that the mass of the slurry is shared between the etOH and the powders, so the above sum is an overestimate. We probably won't collect all the powder either. So we multiply the total mass by 0.85 to account for this. This factor is totally a guess tbh!
            """
            ethanol_g_per_ul = (
                0.789 / 1000
            )  # 0.789 g/cm^3 = 0.789 g/mL = 0.789 g/1000 uL

            self.min_transfer_mass = self.transfer_volume * ethanol_g_per_ul
            for powder, mass in powder_dispenses.items():
                self.min_transfer_mass += mass
            self.min_transfer_mass *= 0.85

        self.allow_replicates = allow_replicates
        if not allow_replicates and replicates > 1:
            raise ValueError(
                "Invalid replicate settings: you said replicates={replicates}, but set allow_replicates to False. Can't have more than one replicate if replicates are not allowed!"
            )
        self.replicates = replicates
        if time_added is None:
            self.time_added = datetime.now()
        else:
            self.time_added = time_added

    def to_json(self):
        return {
            "CrucibleReplicates": self.replicates,
            "HeatingDuration": int(self.heating_duration),
            "EthanolDispenseVolume": int(self.ethanol_volume)
            * self.replicates,  # total volume of ethanol to dispense for all replicates
            "MinimumTransferMass": round(self.min_transfer_mass, 5),
            "MixerDuration": round(self.mixer_duration),
            "MixerSpeed": round(self.mixer_speed),
            "PowderDispenses": [
                {"PowderName": powder, "TargetMass": round(mass * self.replicates, 5)}
                for powder, mass in self.powder_dispenses.items()
            ],
            "TargetTransferVolume": int(self.transfer_volume),
            "time_added": self.time_added.isoformat(),
        }

    def to_labman_json(self, position: int):
        """
        Example:
            {
            "CrucibleReplicates": 2,
            "HeatingDuration": 300,
            "EthanolDispenseVolume": 10000,
            "MinimumTransferMass": 5,
            "MixerDuration": 99455364,
            "MixerSpeed": 2000,
            "Position": 1,
            "PowderDispenses": [
                {
                "PowderName": "Manganese Oxide",
                "TargetMass": 10
                },
                {
                "PowderName": "Lithium carbonate",
                "TargetMass": 10
                }
            ],
            "TargetTransferVolume": 10000
            },
        """
        j = self.to_json()
        j.pop("time_added")
        j["Position"] = position
        return j

    @classmethod
    def from_json(cls, json: Dict):
        return cls(
            powder_dispenses={
                v["PowderName"]: v["TargetMass"] for v in json["PowderDispenses"]
            },
            heating_duration_s=json["HeatingDuration"],
            ethanol_volume_ul=(
                json["EthanolDispenseVolume"] / json["CrucibleReplicates"]
            ),  # our InputFile class assumes that the ethanol volume is *per replicate*
            transfer_volume_ul=json["TargetTransferVolume"],
            mixer_speed_rpm=json["MixerSpeed"],
            mixer_duration_s=json["MixerDuration"],
            min_transfer_mass_g=json["MinimumTransferMass"],
            replicates=json["CrucibleReplicates"],
            time_added=datetime.fromisoformat(json["time_added"]),
        )

    @property
    def age(self) -> int:
        """The age (seconds) of this InputFile.

        Returns:
            int: age (seconds)
        """
        return (datetime.now() - self.time_added).seconds

    @property
    def max_replicates(self) -> int:
        """The maximum number of replicates this InputFile can support.

        Returns:
            int: maximum number of replicates
        """
        return math.floor(self.MAX_JAR_VOLUME_UL / self.ethanol_volume)

    @property
    def can_accept_another_replicate(self) -> bool:
        """Whether this InputFile can accept another replicate.

        Returns:
            bool: True if this InputFile can accept another replicate, False otherwise.
        """
        # return False  # TODO uncomment when we are ready to support replicates
        if not self.allow_replicates:
            return False
        else:
            return self.replicates < self.max_replicates

    def __repr__(self):
        val = "<InputFile:"
        for powder, mass in self.powder_dispenses.items():
            val += f" {powder} +"
        val = val[:-2] + f", {self.replicates} replicates>"
        return val

    def __eq__(self, other):
        if not isinstance(other, InputFile):
            return False
        this = self.to_json()
        that = other.to_json()
        dont_consider_for_equality = ["CrucibleReplicates", "time_added"]

        for each in [this, that]:
            each["EthanolDispenseVolume"] /= each["CrucibleReplicates"]
            for powder in each["PowderDispenses"]:
                powder["TargetMass"] /= each["CrucibleReplicates"]
            each.pop("CrucibleReplicates", None)
            each.pop("time_added", None)

        for key in dont_consider_for_equality:
            this.pop(key, None)
            that.pop(key, None)

        return this == that


class SampleTrackingError(Exception):
    """Indicates that the workflow is not able to maintain sample tracking. This usually happens by incorrect combinations of replicates and sample labelling."""


class Workflow:
    MAX_CRUCIBLES: int = 16
    INVALID_CHARACTERS: List[str] = [":", "\t", "\n", "\r", "\0", "\x0b"]

    def __init__(self, name: str):
        if any([c in self.INVALID_CHARACTERS for c in name]):
            raise ValueError(
                f"Invalid character in name: {name}. The name must contain characters valid in a Windows filepath."
            )
        self.name = name
        self.__inputs = []
        self.__inputfile_to_sample_map: Dict[
            int, List[Any]
        ] = {}  # maps index of inputfile to list of associated samples.

    def add_input(self, inputfile: InputFile, sample: Any = None):
        """Add an InputFile to this Workflow.

        Args:
            inputfile (InputFile): InputFile. This holds instructions for the preparation of a crucible(s).
            sample (Any, optional): An identifier to link this InputFile to a sample. This is used to eventually map mixing pots and crucibles back to the samples they contain. Primarily for ALabOS workflow management. Defaults to None.

        Raises:
            WorkflowFullError: No more crucibles can be added to this workflow.
            SampleTrackingError: Sample tracking was violated when trying to add an inputfile. In general, to address sample tracking issues when building a Workflow, you have two options:
            1. Submit the inputfile multiple times (once for each replicate) and pass the sample to each call to `add_input`. These will be merged into a single inputfile with the correct number of replicates automatically (if possible). Individual submission allows us to track which sample(s) are associated with each mixing pot and, ultimately, each final crucible position in the workflow.

            2. Rebuild this workflow without sample tracking (by passing `sample=None` (default) to `Workflow.add_input` for all inputs). This results in a valid workflow for the Labman, but WILL BREAK ALABOS WORKFLOW TRACKING. This is not recommended unless you are sure that you will not be using ALabOS to manage your workflow.
        """
        if (self.required_crucibles + inputfile.replicates) > self.MAX_CRUCIBLES:
            raise WorkflowFullError(
                f"This workflow is too full ({self.required_crucibles}/{self.MAX_CRUCIBLES} crucibles) to accomomdate this input ({inputfile.replicates} crucibles)!"
            )

        ## Ensure that adding this inputfile will not violate our sample tracking routine.
        tracking_this_sample = sample is not None
        sampletracking_broken = False
        if tracking_this_sample:
            if inputfile.replicates > 1:
                sampletracking_broken = True
                initial_message = "Cannot add inputfiles with >1 replicates because we are tracking the samples attached to each inputfile!"
            if not self.samples_are_being_tracked:
                sampletracking_broken = True
                initial_message = "Cannot track the sample for this inputfile because we have already added inputfiles to this workflow without sample tracking! Please rebuild this workflow without sample tracking."
        elif not tracking_this_sample and self.samples_are_being_tracked:
            sampletracking_broken = True
            initial_message = "Cannot add this inputfile without sample tracking, because we have already added inputfiles to this workflow with sample tracking! Please add this inputfile with sample tracking (by passing `sample=...` to `Workflow.add_input`), or rebuild this workflow without sample tracking.)"

        if self.required_crucibles == 0:
            sampletracking_broken = False  # we havent added any inputfiles yet, so we can do whatever for this inputfile.
        if sampletracking_broken:
            raise SampleTrackingError(
                f"""{initial_message}

    The previous sentence was specific to the current error mode. In general, to address sample tracking issues when building a Workflow, you have two options: 
        1. Submit the inputfile multiple times (once for each replicate) and pass the sample to each call to `add_input`. These will be merged into a single inputfile with the correct number of replicates automatically (if possible). Individual submission allows us to track which sample(s) are associated with each mixing pot and, ultimately, each final crucible position in the workflow.

        2. Rebuild this workflow without sample tracking (by passing `sample=None` (default) to `Workflow.add_input` for all inputs). This results in a valid workflow for the Labman, but WILL BREAK ALABOS WORKFLOW TRACKING. 
    
"""
            )

        ## Sample tracking was not violated. Now we either merge the inputfile into an existing one as replicate(s), or we add it as a new inputfile. We will fill existing inputfiles first. This inputfile may partially fill a matching existing inputfile. For example, if our inputfile has 4 replicates, but the existing match has room for 2 more replicates, we would fill the existing inputfile with 2 replicates and append the rest of this new inputfile with 2 replicates. Note that sample tracking only works when adding inputfiles with 1 replicate, so this partial filling does not violate sample tracking.

        inputfile_index = None
        if inputfile.allow_replicates:
            # try to merge this inputfile with an existing one
            for idx, (existing_inputfile, sample_list) in enumerate(self.__inputs):
                if inputfile != existing_inputfile:
                    # not a matching inputfile
                    continue
                while (
                    existing_inputfile.can_accept_another_replicate
                    and inputfile.replicates > 0
                ):
                    existing_inputfile.replicates += 1
                    sample_list.append(sample)
                    inputfile.replicates -= 1
                    inputfile_index = idx
                if inputfile.replicates == 0:
                    break

        if (
            inputfile.replicates > 0
        ):  # we couldn't fully merge the inputfile with an existing one(s), or replicates were not enabled for this inputfile.
            self.__inputs.append([inputfile, [sample]])

    def to_json(
        self,
        quadrant_index: int,
        available_positions: List[int],
        return_sample_tracking: bool = False,
    ) -> dict:
        if return_sample_tracking and not self.samples_are_being_tracked:
            raise ValueError(
                "Cannot return sample tracking information because we were not tracking samples for this workflow!"
            )

        if len(available_positions) < self.required_jars:
            raise ValueError(
                f"Insufficient available mixing pots ({len(available_positions)}) to accomodate this workflow (requires 4 {self.required_jars})!"
            )
        data = {
            "WorkflowName": self.name,
            "Quadrant": quadrant_index,
            "InputFile": [],
        }

        # sort inputfiles from longest -> shortest heating duration (ethanol drying time), minimizing the overall workflow time as inputfiles are executed in this order.

        sorted_inputs = sorted(
            self.__inputs,
            key=lambda x: x[0].heating_duration,
            reverse=True,
        )

        sample_mapping = {}  # {mixingpot_position: [sample1, sample2, ...], ...}
        for (inputfile, samples_within_inputfile), position in zip(
            sorted_inputs, available_positions
        ):
            inputfile: InputFile
            data["InputFile"].append(inputfile.to_labman_json(position=position))
            sample_mapping[position] = samples_within_inputfile

        if return_sample_tracking:
            return data, sample_mapping
        else:
            return data

    def __len__(self):
        return len(self.inputfiles)

    def __repr__(self):
        return f"""<Workflow: {self.required_jars} jars, {self.required_crucibles} crucibles, {len(self.required_powders)} unique powders>"""

    @property
    def required_ethanol_volume_ul(self) -> int:
        """The total volume of ethanol (in microliters) required to execute this workflow"""
        return sum(
            [input.ethanol_volume * input.replicates for input in self.inputfiles]
        )

    @property
    def required_jars(self) -> int:
        """The number of jar required to execute this workflow

        Returns:
            int: number of jars
        """
        return len(self.inputfiles)

    @property
    def required_crucibles(self) -> int:
        """The number of crucibles required to execute this workflow

        Returns:
            int: number of crucibles
        """
        return sum([input.replicates for input in self.inputfiles])

    @property
    def required_powders(self) -> Dict[str, float]:
        """The masses of powders required to execute this workflow

        Returns:
            Dict[str, float]: dictionary of powders and their required masses (in grams)
        """
        powders = {}
        for input in self.inputfiles:
            for powder, mass in input.powder_dispenses.items():
                if powder not in powders:
                    powders[powder] = 0
                powders[powder] += mass * input.replicates
        return powders

    @property
    def inputfiles(self) -> List[InputFile]:
        """The inputs in this workflow.

        Returns:
            List[InputFile]: list of inputs
        """
        return [inputfile for (inputfile, sample_list) in self.__inputs]

    @property
    def samples_are_being_tracked(self) -> bool:
        for inputfile, sample_list in self.__inputs:
            if any([sample is not None for sample in sample_list]):
                return True  # we are tracking samples for at least one inputfile
        return False
