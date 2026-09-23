<script>
  import nfdiLogo from "/nfdi_rgb_Wortmarke_Zusatz_quer.png";
  import cziLogo from "/czi-logo-chan-zuckerberg-initiative-logo.png";
  let base = import.meta.env.BASE_URL;
</script>

<!-- base element used to define relative links -->
<base href={base} />
<div>
  <h2>Introduction</h2>
  <p>
    Zowser is an OME-Zarr browser based on the <a
      href="https://forum.image.sc/t/ome2024-ngff-challenge/97363"
      >2024 OME-NGFF Challenge</a
    >, conceived at the
    <a href="https://www.openmicroscopy.org/events/ome-community-meeting-2024/">
      OME Annual Community Meeting</a
    >
    in Dundee in May 2024.
  </p>
  <h2>Acknowledgements</h2>
  <p>
    Coordination of the challenge was supported by the <a
      href="https://www.nfdi.de/"
      >German National Research Data Initiative (NFDI)</a
    >
    and the
    <a href="https://chanzuckerberg.com/">Chan Zuckerberg Initiative</a>:
  </p>

  <table>
    <tr>
      <td><img src={nfdiLogo} alt="NFDI Logo" width="45%" /></td>
      <td
        ><img
          src={cziLogo}
          alt="Chan Zuckerberg Initiative Logo"
          width="45%"
        /></td
      >
    </tr>
  </table>
</div>

<style>
  div {
    margin: 20px;
  }
</style>
